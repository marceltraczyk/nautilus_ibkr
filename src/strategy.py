from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class ForexPricePrinter(Strategy):
    def __init__(self, instrument_id: InstrumentId):
        super().__init__()
        self.instrument_id = instrument_id

    def on_start(self):
        self.subscribe_quote_ticks(self.instrument_id)
        self.log.info(f"Rozpoczęto subskrypcję cen na żywo dla: {self.instrument_id}")

    def on_quote_tick(self, tick: QuoteTick):
        spread = tick.ask_price - tick.bid_price

        self.log.info(
            f"[{tick.instrument_id}] BID: {tick.bid_price} | ASK: {tick.ask_price} | SPREAD: {spread}"
        )
