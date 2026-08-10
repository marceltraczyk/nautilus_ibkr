from nautilus_trader.adapters.interactive_brokers.common import IB
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Quantity

from sma_cross import SmaCrossStrategy, SmaCrossConfig


def run_trading_node(config_node: TradingNodeConfig) -> None:
    node = TradingNode(config=config_node)

    try:
        node.add_data_client_factory(IB, InteractiveBrokersLiveDataClientFactory)
        node.add_exec_client_factory(IB, InteractiveBrokersLiveExecClientFactory)

        node.build()

        strategy_config = SmaCrossConfig(
            instrument_id=InstrumentId.from_str("EUR/USD.IDEALPRO"),
            bar_type=BarType.from_str("EUR/USD.IDEALPRO-1-MINUTE-MID-EXTERNAL"),
            fast_sma=5,
            slow_sma=15,
            trade_size=Quantity.from_int(1000)  # Ustawiamy 1K jak z Twoich wcześniejszych screenów
                )
                
        # 2. Inicjalizujemy strategię
        strategy = SmaCrossStrategy(config=strategy_config)
        
        # 3. Przekazujemy strategię do węzła
        # 3. Przekazujemy strategię do obiektu trader wewnątrz węzła
        node.trader.add_strategy(strategy)

        node.run()
    finally:
        node.dispose()
