"""Download 15-minute FX bars from Interactive Brokers into a Parquet catalog.

Resumable: re-running skips whatever is already stored.
"""

import asyncio
import datetime
import os
import sys
import time
from collections import deque
from pathlib import Path

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
from nautilus_trader.model.data import Bar
from nautilus_trader.persistence.catalog import ParquetDataCatalog


# --- Configuration ----------------------------------------------------------
CATALOG_PATH = Path(__file__).parent / "parquet_data"

# FX on IDEALPRO has no trades, so LAST returns nothing
BAR_SPEC = "15-MINUTE-MID"

# Naive on purpose: request_bars() takes the timezone separately via tz_name,
# and pandas rejects a tz-aware datetime alongside a tz argument.
END_DATE = datetime.datetime.now(datetime.timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0, tzinfo=None,
)
START_DATE = (pd.Timestamp(END_DATE) - pd.DateOffset(years=10)).to_pydatetime()

# One IB request per window - a 10-year window would be rejected
CHUNK = "3MS"

# IB allows 60 historical requests per 10 minutes - 55 leaves headroom
MAX_REQUESTS_PER_WINDOW = 55
PACING_WINDOW = 600.0

MAX_RETRIES = 2
RETRY_SLEEP = 5.0
PACING_VIOLATION_SLEEP = 60.0
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


class PacingLimiter:
    """Keeps the request rate under IB's historical data cap.

    IB counts over a sliding window, so tracking send times beats a fixed sleep:
    slow requests consume the wait on their own.
    """

    def __init__(self, max_requests: int, window: float) -> None:
        self._max = max_requests
        self._window = window
        self._sent: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()

            while self._sent and now - self._sent[0] > self._window:
                self._sent.popleft()

            if len(self._sent) < self._max:
                self._sent.append(now)
                return

            wait = self._window - (now - self._sent[0]) + 1.0
            print(f"     pacing: sleeping {wait:.0f}s to stay under IB's cap", flush=True)
            await asyncio.sleep(wait)


def build_chunks(start, end):
    """Split the full range into request windows, keeping the final partial one."""
    edges = pd.date_range(start=start, end=end, freq=CHUNK)
    edges = edges[edges > pd.Timestamp(start)]
    edges = pd.DatetimeIndex([pd.Timestamp(start)]).append(edges)

    if edges[-1] < pd.Timestamp(end):
        edges = edges.append(pd.DatetimeIndex([pd.Timestamp(end)]))

    return [
        (edges[i].to_pydatetime(), edges[i + 1].to_pydatetime())
        for i in range(len(edges) - 1)
    ]


def stored_cutoff(catalog, bar_type: str) -> int:
    """Newest bar timestamp (ns) already stored for this bar type, or 0."""
    try:
        last = catalog.query_last_timestamp(Bar, bar_type)
    except Exception:
        return 0

    return 0 if last is None else int(last.value)


async def request_chunk(client, limiter, contract, chunk_start, chunk_end):
    """Request one window, retrying on failure. Returns None when it gave up."""
    for attempt in range(1, MAX_RETRIES + 2):
        await limiter.acquire()

        try:
            return await client.request_bars(
                bar_specifications=[BAR_SPEC],
                start_date_time=chunk_start,
                end_date_time=chunk_end,
                tz_name="UTC",
                contracts=[contract],
                use_rth=False,  # FX trades around the clock - RTH would drop most bars
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as error:
            message = str(error)
            print(
                f"     attempt {attempt} failed "
                f"({chunk_start.date()} -> {chunk_end.date()}): {message}",
                flush=True,
            )

            if attempt > MAX_RETRIES:
                return None

            # A pacing violation needs a long cool-off, anything else a short one
            cool_off = PACING_VIOLATION_SLEEP if "pacing" in message.lower() else RETRY_SLEEP
            await asyncio.sleep(cool_off)

    return None


async def download_pair(client, catalog, limiter, base, quote, chunks, stats):
    """Download one currency pair window by window, skipping what is already stored."""
    contract = IBContract(secType="CASH", symbol=base, currency=quote, exchange="IDEALPRO")

    instruments = await client.request_instruments(contracts=[contract])
    if not instruments:
        print(f"  !! {base}/{quote}: instrument not found at IB - skipping", flush=True)
        stats["failed_pairs"].append(f"{base}/{quote}")
        return

    instrument = instruments[0]
    if str(instrument.id) not in stats["known_instruments"]:
        catalog.write_data(instruments)
        stats["known_instruments"].add(str(instrument.id))

    bar_type = f"{instrument.id}-{BAR_SPEC}-EXTERNAL"

    # Read the resume point once per pair, not once per window
    cutoff = stored_cutoff(catalog, bar_type)
    saved = 0
    skipped = 0

    for number, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        if cutoff and cutoff >= int(pd.Timestamp(chunk_end).value):
            skipped += 1
            continue

        bars = await request_chunk(client, limiter, contract, chunk_start, chunk_end)

        if bars is None:
            print(f"     [{number:>2}/{len(chunks)}] {chunk_start.date()} -> failed", flush=True)
            stats["failed_chunks"] += 1
            continue

        stats["requests"] += 1

        # IB anchors on end_date_time and counts trading days backwards, so it
        # returns bars from before chunk_start - writing those would overlap
        # the previous file, which the catalog rejects
        fresh = [bar for bar in bars if bar.ts_init > cutoff]

        if fresh:
            catalog.write_data(fresh)
            cutoff = max(bar.ts_init for bar in fresh)
            saved += len(fresh)

        print(
            f"     [{number:>2}/{len(chunks)}] {chunk_start.date()} -> {chunk_end.date()}   "
            f"{len(fresh):>6,} bars   (pair total {saved:,})",
            flush=True,
        )

    resumed = f", {skipped} windows already stored" if skipped else ""
    print(f"  -> {base}/{quote}: {saved:,} bars stored{resumed}", flush=True)
    stats["bars"] += saved


async def main() -> None:
    # 1. Authenticate and start the IB Gateway container
    load_dotenv()
    username = os.environ.get("TWS_USERNAME")
    password = os.environ.get("TWS_PASSWORD")

    if not username or not password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    gateway = DockerizedIBGateway(config=DockerizedIBGatewayConfig(
        username=username,
        password=password,
        trading_mode="paper",
        read_only_api=True,
        timeout=300,
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
        host="127.0.0.1",
        port=4002,
        client_id=5,
        log_level="WARN",
    )

    catalog = ParquetDataCatalog(CATALOG_PATH)
    chunks = build_chunks(START_DATE, END_DATE)
    limiter = PacingLimiter(MAX_REQUESTS_PER_WINDOW, PACING_WINDOW)

    try:
        known_instruments = {str(i.id) for i in catalog.instruments()}
    except Exception:
        known_instruments = set()

    stats = {
        "bars": 0,
        "requests": 0,
        "failed_chunks": 0,
        "failed_pairs": [],
        "known_instruments": known_instruments,
    }

    started = time.time()
    crashed = False

    try:
        await client.connect()
        # IB's historical data farm connects after the socket does
        await asyncio.sleep(5)

        total_requests = len(FX_PAIRS) * len(chunks)
        estimate = total_requests / MAX_REQUESTS_PER_WINDOW * PACING_WINDOW / 3600

        print(f"Catalog:   {CATALOG_PATH}")
        print(f"Bar spec:  {BAR_SPEC}")
        print(f"Range:     {START_DATE.date()} -> {END_DATE.date()}")
        print(f"Pairs:     {len(FX_PAIRS)}   windows/pair: {len(chunks)}   "
              f"requests: {total_requests}")
        print(f"Estimated: {estimate:.1f} h at IB's pacing limit "
              f"(far less when resuming)\n", flush=True)

        # 3. Download every pair, one at a time
        for index, (base, quote) in enumerate(FX_PAIRS, start=1):
            elapsed = (time.time() - started) / 60
            remaining = total_requests - stats["requests"]
            eta = remaining / MAX_REQUESTS_PER_WINDOW * PACING_WINDOW / 60

            print(f"\n[{index}/{len(FX_PAIRS)}] {base}/{quote}   "
                  f"(elapsed {elapsed:.0f} min, ETA {eta:.0f} min, "
                  f"{stats['bars']:,} bars so far)", flush=True)
            await download_pair(client, catalog, limiter, base, quote, chunks, stats)

    except Exception as error:
        crashed = True
        print(f"\nFatal error: {error}\n")
    finally:
        # 4. Report, then shut down the client before the gateway it talks through
        minutes = (time.time() - started) / 60
        print("\n" + "=" * 60)
        print(f"Bars stored:      {stats['bars']:,}")
        print(f"Requests sent:    {stats['requests']:,}")
        print(f"Failed windows:   {stats['failed_chunks']}")
        print(f"Failed pairs:     {stats['failed_pairs'] or 'none'}")
        print(f"Elapsed:          {minutes:.0f} min")
        print("=" * 60)

        client._client.stop()
        await asyncio.sleep(1)

        print("\nStopping IB Gateway container...\n")
        gateway.stop()

    if crashed or stats["failed_pairs"] or stats["failed_chunks"]:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
