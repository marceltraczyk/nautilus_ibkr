from nautilus_trader.adapters.interactive_brokers.common import IB
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId

from strategy import ForexPricePrinter


def run_trading_node(config_node: TradingNodeConfig) -> None:
    node = TradingNode(config=config_node)

    try:
        node.add_data_client_factory(IB, InteractiveBrokersLiveDataClientFactory)
        node.add_exec_client_factory(IB, InteractiveBrokersLiveExecClientFactory)

        instrument_id = InstrumentId.from_str("EUR/USD.IDEALPRO")
        strategy = ForexPricePrinter(instrument_id=instrument_id)
        node.trader.add_strategy(strategy)

        node.build()

        node.run()
    finally:
        node.dispose()
