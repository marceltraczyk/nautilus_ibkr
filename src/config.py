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

# 1-MINUTE keeps the demo responsive. The strategy needs `bb_period` bars before
# it can emit a signal, so 15-MINUTE would mean waiting over five hours for the
# first one. Switch to 15-MINUTE to match the timeframe used in the backtest.
BAR_TYPE = f"{INSTRUMENT_ID}-1-MINUTE-MID-EXTERNAL"

# 100_000 EUR is one standard lot
TRADE_SIZE = 100_000

# Both entry points reach the gateway at the same address: the dockerized
# gateway publishes 4002 on localhost, and a desktop IB Gateway in paper mode
# listens there as well. Override in .env when yours differs.
IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4002"))

# Instrument provider configuration
instrument_provider_config = InteractiveBrokersInstrumentProviderConfig(
    symbology_method=SymbologyMethod.IB_SIMPLIFIED,
    load_ids=frozenset([INSTRUMENT_ID]),
)

# Data client configuration
data_client_config = InteractiveBrokersDataClientConfig(
    ibg_host=IB_HOST,
    ibg_port=IB_PORT,
    ibg_client_id=1,
    use_regular_trading_hours=False,  # FX trades around the clock
    market_data_type=IBMarketDataTypeEnum.REALTIME,
    instrument_provider=instrument_provider_config,
)

# Execution client configuration - a separate client id, IB requires one per connection
exec_client_config = InteractiveBrokersExecClientConfig(
    ibg_host=IB_HOST,
    ibg_port=IB_PORT,
    ibg_client_id=2,
    account_id=os.environ.get("TWS_ACCOUNT"),  # Your paper trading account
    instrument_provider=instrument_provider_config,
    routing=RoutingConfig(default=True),
)

# Trading node configuration
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
