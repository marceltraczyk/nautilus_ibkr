import os
import sys
import time

from dotenv import load_dotenv
from nautilus_trader.adapters.interactive_brokers.gateway import (
    DockerizedIBGateway,
    DockerizedIBGatewayConfig,
)

#from config import config_node
#from runner import run_trading_node


def main() -> None:
    load_dotenv()

    ibkr_username = os.environ.get("TWS_USERNAME")
    ibkr_password = os.environ.get("TWS_PASSWORD")

    if not ibkr_username or not ibkr_password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    # 1. IB Gateway Docker configuration
    gateway_config = DockerizedIBGatewayConfig(
        username=ibkr_username,
        password=ibkr_password,
        trading_mode="paper",  # "paper" or "live"
        read_only_api=False,  # Set to False to allow order execution
        timeout=300,  # Startup timeout in seconds
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
        time.sleep(5)  # Allow IB Gateway API socket server to fully initialize

        #run_trading_node(config_node)
    except KeyboardInterrupt:
        print("\nGracefully shutting down market data stream...")
    except Exception as error:  # noqa: BLE001 Should be fixed to a more specific exception type if possible
        print(f"\nERROR: {error}")
    finally:
        print("\nStopping IB Gateway container...")
        gateway.stop()


if __name__ == "__main__":
    main()
