import os

from dotenv import load_dotenv
from nautilus_trader.adapters.interactive_brokers.common import IB
from nautilus_trader.adapters.interactive_brokers.config import (
    IBMarketDataTypeEnum,
    InteractiveBrokersDataClientConfig,
    InteractiveBrokersExecClientConfig,
    InteractiveBrokersInstrumentProviderConfig,
    SymbologyMethod,
)
from nautilus_trader.config import (
    LiveDataEngineConfig,
    LoggingConfig,
    RoutingConfig,
    TradingNodeConfig,
)

load_dotenv()

# --- What to trade ----------------------------------------------------------
INSTRUMENT_ID = "EUR/USD.IDEALPRO"

# The strategy needs `bb_period` bars before its first signal, so 1-MINUTE keeps
# the demo responsive. Use 15-MINUTE to match the backtest.
BAR_TYPE = f"{INSTRUMENT_ID}-1-MINUTE-MID-EXTERNAL"

# One standard lot
TRADE_SIZE = 100_000

# Both the dockerized and the desktop gateway listen here in paper mode
IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4002"))

instrument_provider_config = InteractiveBrokersInstrumentProviderConfig(
    symbology_method=SymbologyMethod.IB_SIMPLIFIED,
    load_ids=frozenset([INSTRUMENT_ID]),
)

data_client_config = InteractiveBrokersDataClientConfig(
    ibg_host=IB_HOST,
    ibg_port=IB_PORT,
    ibg_client_id=1,
    use_regular_trading_hours=False,  # FX trades around the clock
    market_data_type=IBMarketDataTypeEnum.REALTIME,
    instrument_provider=instrument_provider_config,
)

# Separate client id - IB requires one per connection
exec_client_config = InteractiveBrokersExecClientConfig(
    ibg_host=IB_HOST,
    ibg_port=IB_PORT,
    ibg_client_id=2,
    account_id=os.environ.get("TWS_ACCOUNT"),  # Your paper trading account
    instrument_provider=instrument_provider_config,
    routing=RoutingConfig(default=True),
)

config_node = TradingNodeConfig(
    trader_id="PAPER-TRADER-001",
    logging=LoggingConfig(log_level="INFO"),
    data_clients={IB: data_client_config},
    exec_clients={IB: exec_client_config},
    data_engine=LiveDataEngineConfig(
        time_bars_timestamp_on_close=False,  # IB standard: use bar open time
        validate_data_sequence=True,  # Discard out-of-sequence bars
    ),
    timeout_connection=90.0,
    timeout_reconciliation=5.0,
    timeout_portfolio=5.0,
    timeout_disconnection=5.0,
    timeout_post_stop=2.0,
)
