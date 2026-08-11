import asyncio
import datetime
import os
import sys

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


async def download_historical_data():
    # 1. Import environment variables from .env file
    load_dotenv()

    ibkr_username = os.environ.get("TWS_USERNAME")
    ibkr_password = os.environ.get("TWS_PASSWORD")

    if not ibkr_username or not ibkr_password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    # 2. Start IB Gateway container
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

    # 3. Connect historic client
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

        # Creating a “parquet” directory
        catalog = ParquetDataCatalog("./backtest/data_catalog")

        # Download and immediately save the instrument
        instruments = await client.request_instruments(contracts=contracts)
        if instruments:
            catalog.write_data(instruments)
            print(f"Instrument recorded: {instruments[0].id}\n")

        # 4. Downloading historical bars for the specified date range
        start_date = datetime.datetime(2025, 1, 1, 0, 0)
        end_date = datetime.datetime(2026, 1, 1, 0, 0)

        print(
            f"Downloading bars: {start_date.strftime('%Y-%m-%d')} -> {end_date.strftime('%Y-%m-%d')}...\n"
        )

        bars = await client.request_bars(
            bar_specifications=["15-MINUTE-MID"],
            start_date_time=start_date,
            end_date_time=end_date,
            tz_name="UTC",
            contracts=contracts,
            use_rth=False,
        )

        if bars:
            catalog.write_data(bars)
            print(f"Downloaded and saved {len(bars)} bars.\n")
        else:
            print("No data available for the specified range.\n")

    except Exception as e:
        print(f"Connection or execution error: {e}\n")
    finally:
        print("Stopping IB Gateway container...\n")
        gateway.stop()


if __name__ == "__main__":
    asyncio.run(download_historical_data())
