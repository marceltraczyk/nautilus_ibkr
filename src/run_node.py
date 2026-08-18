import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nautilus_trader.adapters.interactive_brokers.common import IB
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity

from src.config import BAR_TYPE, INSTRUMENT_ID, TRADE_SIZE
from src.mean_reversion import MeanReversionConfig, MeanReversionStrategy


def run_trading_node(config_node: TradingNodeConfig) -> None:
    """Build the node, attach the strategy and trade until interrupted."""
    node = TradingNode(config=config_node)

    try:
        # 1. Register the IB client factories, then build the node around them
        node.add_data_client_factory(IB, InteractiveBrokersLiveDataClientFactory)
        node.add_exec_client_factory(IB, InteractiveBrokersLiveExecClientFactory)
        node.build()

        # 2. Attach the strategy
        strategy_config = MeanReversionConfig(
            instrument_id=InstrumentId.from_str(INSTRUMENT_ID),
            bar_type=BarType.from_str(BAR_TYPE),
            trade_size=Quantity.from_int(TRADE_SIZE),
        )
        node.trader.add_strategy(MeanReversionStrategy(config=strategy_config))

        # 3. Blocks here, streaming bars and submitting orders, until Ctrl+C
        node.run()
    finally:
        node.dispose()
