import statistics
from collections import deque

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy, StrategyConfig


class SmaCrossConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    fast_sma: int = 5     # Liczba świec dla szybkiej średniej
    slow_sma: int = 15    # Liczba świec dla wolnej średniej
    trade_size: Quantity = Quantity.from_int(100_000)  # Domyślnie 1 lot (100k EUR)


class SmaCrossStrategy(Strategy):
    def __init__(self, config: SmaCrossConfig) -> None:
        super().__init__(config)
        self.prices = deque(maxlen=config.slow_sma)
        self.in_position = False

    def on_start(self) -> None:
        self.log.info("Uruchamiam strategię SMA Cross!")
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        # Konwertujemy cenę na float do prostych obliczeń w Pythonie
        self.prices.append(float(bar.close))

        if len(self.prices) < self.config.slow_sma:
            return

        prices_list = list(self.prices)
        fast_ma = statistics.mean(prices_list[-self.config.fast_sma:])
        slow_ma = statistics.mean(prices_list)

        if fast_ma > slow_ma and not self.in_position:
            self.log.info(f"Sygnał BUY! Fast: {fast_ma:.5f} > Slow: {slow_ma:.5f}")
            self.buy()
            self.in_position = True

        elif fast_ma < slow_ma and self.in_position:
            self.log.info(f"Sygnał SELL! Fast: {fast_ma:.5f} < Slow: {slow_ma:.5f}")
            self.sell()
            self.in_position = False

    def buy(self) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.config.trade_size,
        )
        self.submit_order(order)

    def sell(self) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.config.trade_size,
        )
        self.submit_order(order)