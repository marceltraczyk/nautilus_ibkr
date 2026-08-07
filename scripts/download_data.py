import asyncio
import datetime
import os
import sys
import time

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
    load_dotenv()

    ibkr_username = os.environ.get("TWS_USERNAME")
    ibkr_password = os.environ.get("TWS_PASSWORD")

    if not ibkr_username or not ibkr_password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    # 1. Start IB Gateway container
    gateway_config = DockerizedIBGatewayConfig(
        username=ibkr_username,
        password=ibkr_password,
        trading_mode="paper",
        read_only_api=True,  # tylko dane, nie potrzebujesz zapisu zleceń
        timeout=300,
    )

    print("Starting Interactive Brokers Gateway container...")
    gateway = DockerizedIBGateway(config=gateway_config)
    gateway.start()

    if not gateway.is_logged_in(gateway.container):
        print("\nAUTHENTICATION FAILED:")
        print(gateway.container.logs())
        gateway.stop()
        sys.exit(1)

    print("\nSUCCESS: Authenticated with IB Gateway!")
    time.sleep(5)

    # 2. Now connect the historical client to it (localhost!)
    client = HistoricInteractiveBrokersClient(
        host="127.0.0.1",
        port=4002,
        client_id=5,
    )

    try:
        await client.connect()
        await asyncio.sleep(2)

        contracts = [
            IBContract(secType="CASH", symbol="EUR", currency="USD", exchange="IDEALPRO"),
        ]

        instruments = await client.request_instruments(contracts=contracts)

        bars = await client.request_bars(
            bar_specifications=["1-MINUTE-MID"],
            start_date_time=datetime.datetime(2026, 8, 5, 0, 0),
            end_date_time=datetime.datetime(2026, 8, 6, 0, 0),
            tz_name="UTC",
            contracts=contracts,
            use_rth=False,
        )

        catalog = ParquetDataCatalog("./data_catalog")
        catalog.write_data(instruments)
        catalog.write_data(bars)
    except Exception as e:
        print(f"Błąd połączenia lub wykonania: {e}")
    finally:
        print("\nStopping IB Gateway container...")
        gateway.stop()


if __name__ == "__main__":
    asyncio.run(download_historical_data())