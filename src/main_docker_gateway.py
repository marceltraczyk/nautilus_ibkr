"""Trade through a dockerized IB Gateway that this script starts and stops.

Needs Docker running and TWS_USERNAME / TWS_PASSWORD in .env. For a gateway you
launched yourself use main.py instead.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from nautilus_trader.adapters.interactive_brokers.gateway import (
    DockerizedIBGateway,
    DockerizedIBGatewayConfig,
)

from src.config import config_node
from src.run_node import run_trading_node


def main() -> None:
    load_dotenv()

    username = os.environ.get("TWS_USERNAME")
    password = os.environ.get("TWS_PASSWORD")

    if not username or not password:
        print("Credentials missing in .env file.")
        sys.exit(1)

    # 1. Start the gateway container and confirm the login went through
    gateway = DockerizedIBGateway(config=DockerizedIBGatewayConfig(
        username=username,
        password=password,
        trading_mode="paper",
        read_only_api=False,  # False so the node is allowed to submit orders
        timeout=300,
    ))

    print("Starting Interactive Brokers Gateway container...")
    gateway.start()

    if not gateway.is_logged_in(gateway.container):
        print("\nAUTHENTICATION FAILED: printing container logs:")
        print(gateway.container.logs())
        gateway.stop()
        sys.exit(1)

    print("\nSUCCESS: Authenticated with IB Gateway!")
    time.sleep(5)  # The API socket server needs a moment after the login

    try:
        # 2. Hand over to the node - it runs until Ctrl+C
        run_trading_node(config_node)
    except KeyboardInterrupt:
        print("\nInterrupted, shutting down...")
    finally:
        # 3. Always stop the container, even when the node crashed
        print("\nStopping IB Gateway container...")
        gateway.stop()


if __name__ == "__main__":
    main()
