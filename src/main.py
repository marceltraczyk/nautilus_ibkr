import os
import sys
import time
from dotenv import load_dotenv

from nautilus_trader.adapters.interactive_brokers.common import IB
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.adapters.interactive_brokers.gateway import (
    DockerizedIBGateway,
    DockerizedIBGatewayConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId

from config import config_node
from strategy import ForexPricePrinter


def main() -> None:
    load_dotenv()

    ibkr_username = os.environ.get("TWS_USERNAME")
    ibkr_password = os.environ.get("TWS_PASSWORD")

    if not ibkr_username or not ibkr_password:
        print("CRITICAL ERROR: Credentials missing in .env file.")
        sys.exit(1)

    # 1. IB Gateway Docker configuration
    gateway_config = DockerizedIBGatewayConfig(
        username=ibkr_username,
        password=ibkr_password,
        trading_mode="paper",
        read_only_api=False,
        timeout=300,
    )

    print("Starting Interactive Brokers Gateway container...")
    gateway = DockerizedIBGateway(config=gateway_config)

    try:
        gateway.start()

        if not gateway.is_logged_in(gateway.container):
            print("\nAUTHENTICATION FAILED: Printing container logs:")
            print(gateway.container.logs())
            return

        print("\nSUCCESS: Authenticated with IB Gateway!")
        time.sleep(5)

        node = TradingNode(config=config_node)
        node.add_data_client_factory(IB, InteractiveBrokersLiveDataClientFactory)
        node.add_exec_client_factory(IB, InteractiveBrokersLiveExecClientFactory)

        instrument_id = InstrumentId.from_str("EUR/USD.IDEALPRO")
        strategy = ForexPricePrinter(instrument_id=instrument_id)
        node.trader.add_strategy(strategy)

        print("Budowanie węzła i łączenie z IBKR...")
        node.build()

        print("Uruchamianie strumieniowania cen (naciśnij Ctrl+C aby zatrzymać)...")
        node.run()

    except KeyboardInterrupt:
        print("\nGracefully shutting down market data stream...")
    except Exception as error:
        print(f"\nRUNTIME ERROR: {error}")
    finally:
        print("\nStopping IB Gateway container...")
        gateway.stop()
        if node:
            node.dispose()


if __name__ == "__main__":
    main()