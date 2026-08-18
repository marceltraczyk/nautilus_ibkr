from nautilus_trader.indicators import (
    BollingerBands,
    EfficiencyRatio,
    RelativeStrengthIndex,
)
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy, StrategyConfig


class MeanReversionConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType

    # Bollinger Bands
    bb_period: int = 21
    bb_deviation: float = 2.0

    # Relative Strength Index
    # Nautilus reports RSI on a 0.0-1.0 scale, not the textbook 0-100
    rsi_period: int = 14
    rsi_overbought: float = 0.70
    rsi_oversold: float = 0.30

    # Kaufman Efficiency Ratio - trade only when the market is choppy
    er_period: int = 14
    max_er: float = 0.30

    # The opposite band captures the full swing, the middle band the smaller move
    # back to fair value. Middle wins on 1H - the opposite band holds through too
    # many failed reversions to pay for the extra distance.
    exit_at_opposite_band: bool = False

    # One standard lot
    trade_size: Quantity = Quantity.from_int(100_000)


class MeanReversionStrategy(Strategy):
    def __init__(self, config: MeanReversionConfig) -> None:
        super().__init__(config)

        self.bands = BollingerBands(period=config.bb_period, k=config.bb_deviation)
        self.rsi = RelativeStrengthIndex(period=config.rsi_period)
        self.er = EfficiencyRatio(period=config.er_period)

        self.warmup_target = max(config.bb_period, config.rsi_period, config.er_period)
        self.bars_seen = 0

    def on_start(self) -> None:
        self.log.info("Starting Mean Reversion strategy (Bollinger + RSI + EfficiencyRatio)!")
        self.subscribe_bars(self.config.bar_type)

        self.register_indicator_for_bars(self.config.bar_type, self.bands)
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        self.register_indicator_for_bars(self.config.bar_type, self.er)

        cached_bars = self.cache.bars(self.config.bar_type)

        if cached_bars:
            warmup_length = max(
                self.config.bb_period,
                self.config.rsi_period,
                self.config.er_period,
            )
            # The cache returns bars newest first, so take the newest `warmup_length`
            # and flip them back into chronological order before feeding indicators
            bars_to_warmup = list(cached_bars)[:warmup_length][::-1]
            for bar in bars_to_warmup:
                self.bands.handle_bar(bar)
                self.rsi.handle_bar(bar)
                self.er.handle_bar(bar)

            self.bars_seen = len(bars_to_warmup)
            self.log.info(
                f"Warmed up indicators with {len(bars_to_warmup)} cached bars. "
                f"Bands initialized: {self.bands.initialized}"
            )

    def on_bar(self, bar: Bar) -> None:
        self.bars_seen += 1

        # 1. Wait for the indicators to warm up, reporting progress meanwhile
        if not (self.bands.initialized and self.rsi.initialized and self.er.initialized):
            self.log.info(
                f"Warming up: {self.bars_seen}/{self.warmup_target} bars | close {bar.close}"
            )
            return

        close_price = float(bar.close)
        upper_band = self.bands.upper
        lower_band = self.bands.lower
        middle_band = self.bands.middle

        rsi_val = float(self.rsi.value)
        er_val = float(self.er.value)

        is_long = self.portfolio.is_net_long(self.config.instrument_id)
        is_short = self.portfolio.is_net_short(self.config.instrument_id)
        is_flat = not is_long and not is_short

        # 2. One line per bar showing price against every threshold
        position = "LONG" if is_long else "SHORT" if is_short else "FLAT"
        self.log.info(
            f"[{position}] close {close_price:.5f} | "
            f"bands {lower_band:.5f} / {middle_band:.5f} / {upper_band:.5f} | "
            f"RSI {rsi_val:.2f} (buy <{self.config.rsi_oversold:.2f}, "
            f"sell >{self.config.rsi_overbought:.2f}) | "
            f"ER {er_val:.2f} (trade <{self.config.max_er:.2f})"
        )

        # 3. Exit logic
        long_target = upper_band if self.config.exit_at_opposite_band else middle_band
        short_target = lower_band if self.config.exit_at_opposite_band else middle_band

        if is_long and close_price >= long_target:
            self.log.info(f"Take Profit for LONG! Price {close_price:.5f} reached {long_target:.5f}")
            self.close_all_positions(self.config.instrument_id)
            return

        if is_short and close_price <= short_target:
            self.log.info(f"Take Profit for SHORT! Price {close_price:.5f} reached {short_target:.5f}")
            self.close_all_positions(self.config.instrument_id)
            return

        # 4. Entry logic
        if is_flat:
            # Skip entries when the market is trending too cleanly
            if er_val >= self.config.max_er:
                return

            if close_price < lower_band and rsi_val < self.config.rsi_oversold:
                self.log.info(
                    f"BUY signal! Close: {close_price:.5f} < Lower: {lower_band:.5f} | RSI: {rsi_val:.2f} | ER: {er_val:.2f}"
                )
                self._submit_market_order(OrderSide.BUY)

            elif close_price > upper_band and rsi_val > self.config.rsi_overbought:
                self.log.info(
                    f"SELL signal! Close: {close_price:.5f} > Upper: {upper_band:.5f} | RSI: {rsi_val:.2f} | ER: {er_val:.2f}"
                )
                self._submit_market_order(OrderSide.SELL)

    def _submit_market_order(self, order_side: OrderSide) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=order_side,
            quantity=self.config.trade_size,
        )
        self.submit_order(order)
