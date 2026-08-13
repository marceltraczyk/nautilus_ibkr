import asyncio
import datetime
import os
import sys

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
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog


async def download_historical_data():
    # 1. Authenticate and start the IB Gateway container
    load_dotenv()

    ibkr_username = os.environ.get("TWS_USERNAME")
    ibkr_password = os.environ.get("TWS_PASSWORD")

    if not ibkr_username or not ibkr_password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    gateway_config = DockerizedIBGatewayConfig(
        username=ibkr_username,
        password=ibkr_password,
        trading_mode="paper",
        read_only_api=True,
        timeout=300,
    )

    print("Starting Interactive Brokers Gateway container...\n")
    gateway = DockerizedIBGateway(config=gateway_config)
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

    try:
        await client.connect()
        await asyncio.sleep(2)

        contracts = [
            IBContract(
                secType="CASH", symbol="EUR", currency="USD", exchange="IDEALPRO"
            ),
        ]

        catalog = ParquetDataCatalog("./backtest/data_catalog")

        # 3. Fetch and save instrument metadata
        instruments = await client.request_instruments(contracts=contracts)
        if instruments:
            catalog.write_data(instruments)
            print(f"Instrument recorded: {instruments[0].id}\n")
        instrument_id = instruments[0].id if instruments else InstrumentId.from_str("EUR/USD.IDEALPRO")

        # 4. Download historical bars in 3-month chunks (avoids IB request timeouts)
        start_date = datetime.datetime(2020, 1, 1, 0, 0) # year, month, day, hour, minute
        end_date = datetime.datetime(2026, 1, 1, 0, 0)

        # Creating chunks of 3 months to avoid pacing violation from IBKR
        chunk_edges = pd.date_range(start=start_date, end=end_date, freq="3MS")
        if chunk_edges[-1] < pd.Timestamp(end_date):
            # Grid may not land exactly on end_date - append it so no tail is dropped
            chunk_edges = chunk_edges.append(pd.DatetimeIndex([end_date]))

        all_bars = []
        for i in range(len(chunk_edges) - 1):
            chunk_start = chunk_edges[i].to_pydatetime()
            chunk_end = chunk_edges[i + 1].to_pydatetime()

            print(f"Downloading: {chunk_start.date()} -> {chunk_end.date()}...")

            try:
                bars = await client.request_bars(
                    bar_specifications=["15-MINUTE-MID"],
                    start_date_time=chunk_start,
                    end_date_time=chunk_end,
                    tz_name="UTC",
                    contracts=contracts,
                    use_rth=False,
                )
            except Exception as e:
                # No retry by design - re-run the script later to backfill any gaps
                print(f"  ERROR for this period: {e} — skipping and continuing\n")
                continue

            if not bars:
                print("  No data for this period (0 bars)\n")
                await asyncio.sleep(2)
                continue

            # IB sometimes returns bars extending earlier than requested,
            # causing overlaps with already-saved data — filter those out
            existing = catalog.bars(instrument_ids=[instrument_id])
            max_existing_ts = max((b.ts_init for b in existing), default=0)
            new_bars = [b for b in bars if b.ts_init > max_existing_ts]

            if new_bars:
                catalog.write_data(new_bars)
                all_bars.extend(new_bars)
                print(f"  OK -> {len(new_bars)} new bars saved (skipped {len(bars) - len(new_bars)} duplicates)\n")
            else:
                print(f"  All {len(bars)} bars were already in the catalog — skipping\n")

            await asyncio.sleep(2)  # Sleep to avoid pacing violation

        print(f"\nDone. Total new bars saved: {len(all_bars)}.\n")
    except Exception as e:
        print(f"Connection or execution error: {e}\n")
    finally:
        print("Stopping IB Gateway container...\n")
        gateway.stop()


if __name__ == "__main__":
    asyncio.run(download_historical_data())
    