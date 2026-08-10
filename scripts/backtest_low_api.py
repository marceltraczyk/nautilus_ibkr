from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.config import ExecEngineConfig, RiskEngineConfig

from src.sma_cross import SmaCrossConfig, SmaCrossStrategy


if __name__ == "__main__":
    CATALOG_PATH = "./data_catalog"

    # Reading the relevant files in the directory
    catalog = ParquetDataCatalog(CATALOG_PATH)

    # Returning the list of instruments from the catalog and selecting the first one (EURUSD.IDEALPRO)
    instruments = catalog.instruments()
    eurusd = instruments[0]

    # Returns a list in which each element is a candle, and we select the first one to get the bar type (BarType.MINUTES_1)
    bars = catalog.bars(instrument_ids=[eurusd.id])
    eurusd_bar_type = bars[0].bar_type

    print(f"--> Detected instrument: {eurusd.id}")
    print(f"--> Detected bar type: {eurusd_bar_type}")
    print(f"--> Number of bars loaded into memory: {len(bars)}")

    # 1. Initializing the engine configuration
    engine_config = BacktestEngineConfig(
        trader_id="IBKR-EURUSD-BACKTEST",
        exec_engine=ExecEngineConfig(),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

    # 2. Adding the IDEALPRO Exchange
    IBKR_VENUE = Venue("IDEALPRO")
    engine.add_venue(
        venue=IBKR_VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(10_000, USD)],  # 10,000 USD depozytu
    )

    # 3. Strategy configuration and instantiation
    strategy_config = SmaCrossConfig(
        instrument_id=eurusd.id,
        bar_type=eurusd_bar_type,
        fast_sma=5,
        slow_sma=15,
        trade_size=eurusd.make_qty(100_000),  # Automatycznie dopasowuje precyzję do instrumentu
    )
    strategy = SmaCrossStrategy(config=strategy_config)

    engine.add_strategy(strategy)
    engine.add_instrument(eurusd)
    engine.add_data(bars)

    # 4. Running the backtest
    print("--> Running backtest...")
    engine.run()

    # 5. Generating report contents
    account_report = engine.trader.generate_account_report(IBKR_VENUE)
    fills_report = engine.trader.generate_order_fills_report()
    positions_report = engine.trader.generate_positions_report()
    orders_report = engine.trader.generate_orders_report()

    # Combining into a single formatted string
    full_report = f"""
================================================================================
                        NAUTILUS TRADER BACKTEST REPORT
================================================================================

--- ACCOUNT REPORT ---
{account_report}

--- ORDER FILLS REPORT ---
{fills_report}

--- POSITIONS REPORT ---
{positions_report}

--- ORDERS REPORT ---
{orders_report}
================================================================================
"""

    # Print to stdout/console
    print(full_report)

    # Save report to TXT file
    report_filename = "backtest_results.txt"
    with open(report_filename, "w", encoding="utf-8") as file:
        file.write(full_report)

    print(f"--> Report successfully saved to '{report_filename}'")