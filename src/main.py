"""Trade through an IB Gateway you start yourself.

Log into the paper account and enable the API socket first.
For the dockerized gateway use main_docker_gateway.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config_node
from src.run_node import run_trading_node


def main() -> None:
    print("Connecting to IB Gateway...\n")

    # 1. Runs until Ctrl+C
    try:
        run_trading_node(config_node)
    except KeyboardInterrupt:
        print("\nInterrupted, shutting down...")


if __name__ == "__main__":
    main()
