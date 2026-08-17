import asyncio
import datetime
import os
import sys
import time

import pandas as pd
from dotenv import load_dotenv
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.adapters.interactive_brokers.gateway import (
    DockerizedIBGateway,
    DockerizedIBGatewayConfig,
)
from nautilus_trader.adapters.interactive_brokers.historical.client import (
    HistoricInteractiveBrokersClient,
)
from nautilus_trader.persistence.catalog import ParquetDataCatalog


# --- Configuration ----------------------------------------------------------
CATALOG_PATH = "./data/fx_catalog"
BAR_SPEC = "15-MINUTE-MID"
START_DATE = datetime.datetime(2016, 1, 1, tzinfo=datetime.timezone.utc)
END_DATE = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

CHUNK = "3MS"  # 3-month request windows keep IB from timing out
PACING_SLEEP = 2.0  # IB allows 60 historical requests per 10 minutes
MAX_RETRIES = 2
REQUEST_TIMEOUT = 180

# Base/quote order follows FX convention: EUR > GBP > AUD > NZD > USD > CAD > CHF > JPY.
FX_PAIRS = [
    ("EUR", "USD"), ("USD", "JPY"), ("GBP", "USD"), ("USD", "CHF"),
    ("AUD", "USD"), ("USD", "CAD"), ("NZD", "USD"),
    ("EUR", "JPY"), ("EUR", "GBP"), ("EUR", "CHF"),
    ("EUR", "AUD"), ("EUR", "CAD"),
    ("GBP", "JPY"), ("GBP", "CHF"), ("GBP", "AUD"),
    ("AUD", "JPY"), ("CAD", "JPY"), ("CHF", "JPY"), ("NZD", "JPY"),
    ("AUD", "NZD"),
]


def build_chunks(start, end):
    """Split the full range into request windows, keeping the final partial one."""
    edges = pd.date_range(start=start, end=end, freq=CHUNK, tz="UTC")

    if len(edges) == 0 or edges[0] > pd.Timestamp(start):
        edges = pd.DatetimeIndex([pd.Timestamp(start)]).append(edges)
    if edges[-1] < pd.Timestamp(end):
        edges = edges.append(pd.DatetimeIndex([pd.Timestamp(end)]))

    return [(edges[i].to_pydatetime(), edges[i + 1].to_pydatetime())
            for i in range(len(edges) - 1)]


def latest_saved(catalog, bar_type_str):
    """Return the newest ts_init already stored for this bar type, or 0."""
    try:
        existing = catalog.bars(bar_types=[bar_type_str])
    except Exception:
        return 0

    return max((b.ts_init for b in existing), default=0)


async def download_pair(client, catalog, base, quote, chunks, stats):
    """Download one currency pair chunk by chunk, skipping what is already stored."""
    contract = IBContract(
        secType="CASH", symbol=base, currency=quote, exchange="IDEALPRO"
    )

    instruments = await client.request_instruments(contracts=[contract])
    if not instruments:
        print(f"  !! {base}/{quote}: instrument not found at IB - skipping")
        stats["failed_pairs"].append(f"{base}/{quote}")
        return

    catalog.write_data(instruments)
    instrument_id = instruments[0].id
    bar_type_str = f"{instrument_id}-{BAR_SPEC}-EXTERNAL"

    saved = 0
    for chunk_start, chunk_end in chunks:
        # Resume support: skip windows that are already fully stored
        cutoff = latest_saved(catalog, bar_type_str)
        if cutoff and pd.Timestamp(cutoff, unit="ns", tz="UTC") >= pd.Timestamp(chunk_end):
            continue

        bars = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                bars = await client.request_bars(
                    bar_specifications=[BAR_SPEC],
                    start_date_time=chunk_start,
                    end_date_time=chunk_end,
                    tz_name="UTC",
                    contracts=[contract],
                    use_rth=False,
                    timeout=REQUEST_TIMEOUT,
                )
                break
            except Exception as e:
                print(f"     attempt {attempt} failed ({chunk_start.date()}): {e}")
                bars = None
                if attempt <= MAX_RETRIES:
                    await asyncio.sleep(5)

        if not bars:
            stats["failed_chunks"] += 1
            await asyncio.sleep(PACING_SLEEP)
            continue

        # IB often returns bars earlier than requested, which would overlap files
        # already in the catalog and break its disjoint-interval invariant
        fresh = [b for b in bars if b.ts_init > cutoff]
        if fresh:
            catalog.write_data(fresh)
            saved += len(fresh)

        stats["requests"] += 1
        await asyncio.sleep(PACING_SLEEP)

    print(f"  -> {base}/{quote}: {saved:,} bars stored")
    stats["bars"] += saved


async def main():
    # 1. Authenticate and start the IB Gateway container
    load_dotenv()
    username = os.environ.get("TWS_USERNAME")
    password = os.environ.get("TWS_PASSWORD")

    if not username or not password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    gateway = DockerizedIBGateway(config=DockerizedIBGatewayConfig(
        username=username, password=password,
        trading_mode="paper", read_only_api=True, timeout=300,
    ))

    print("Starting Interactive Brokers Gateway container...\n")
    gateway.start()

    if not gateway.is_logged_in(gateway.container):
        print("AUTHENTICATION FAILED:\n")
        print(gateway.container.logs())
        gateway.stop()
        sys.exit(1)
    print("SUCCESS: Authenticated with IB Gateway!\n")

    # 2. Connect the historical data client
    client = HistoricInteractiveBrokersClient(
        host="127.0.0.1", port=4002, client_id=5, log_level="WARN",
    )

    stats = {"bars": 0, "requests": 0, "failed_chunks": 0, "failed_pairs": []}
    started = time.time()

    try:
        await client.connect()
        # IB's historical data farm (cashhmds) connects after the socket does
        await asyncio.sleep(5)

        catalog = ParquetDataCatalog(CATALOG_PATH)
        chunks = build_chunks(START_DATE, END_DATE)

        print(f"Catalog:   {CATALOG_PATH}")
        print(f"Bar spec:  {BAR_SPEC}")
        print(f"Range:     {START_DATE.date()} -> {END_DATE.date()}")
        print(f"Pairs:     {len(FX_PAIRS)}   chunks/pair: {len(chunks)}   "
              f"total requests: {len(FX_PAIRS) * len(chunks)}\n")

        # 3. Download every pair, one at a time
        for i, (base, quote) in enumerate(FX_PAIRS, start=1):
            elapsed = time.time() - started
            print(f"[{i}/{len(FX_PAIRS)}] {base}/{quote}   "
                  f"(elapsed {elapsed/60:.0f} min, {stats['bars']:,} bars so far)")
            await download_pair(client, catalog, base, quote, chunks, stats)

    except Exception as e:
        print(f"\nFatal error: {e}\n")
    finally:
        # 4. Report and shut down
        mins = (time.time() - started) / 60
        print("\n" + "=" * 60)
        print(f"Bars stored:      {stats['bars']:,}")
        print(f"Requests sent:    {stats['requests']:,}")
        print(f"Failed chunks:    {stats['failed_chunks']}")
        print(f"Failed pairs:     {stats['failed_pairs'] or 'none'}")
        print(f"Elapsed:          {mins:.0f} min")
        print("=" * 60)
        print("\nStopping IB Gateway container...\n")
        gateway.stop()


if __name__ == "__main__":
    asyncio.run(main())