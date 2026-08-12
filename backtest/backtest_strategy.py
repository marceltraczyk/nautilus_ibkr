import sys
sys.path.insert(0, "/home/marce/nautilus_ikbr")

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import ExecEngineConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pathlib import Path
from nautilus_trader.analysis import create_tearsheet
from nautilus_trader.model.currencies import USD

from src.mean_reversion import MeanReversionConfig, MeanReversionStrategy


if __name__ == "__main__":
    # 1. Initialize the data catalog and load the EUR/USD instrument and its bars
    CATALOG_PATH = "./backtest/data_catalog"

    catalog = ParquetDataCatalog(CATALOG_PATH)

    instruments = catalog.instruments()
    eurusd = instruments[0]

    bars = catalog.bars(instrument_ids=[eurusd.id])
    eurusd_bar_type = bars[0].bar_type

    print(f"Detected instrument: {eurusd.id}")
    print(f"Detected bar type: {eurusd_bar_type}")
    print(f"Number of bars loaded into memory: {len(bars)}")

    # 2. Initializing the engine configuration
    engine_config = BacktestEngineConfig(
        trader_id="IBKR-BACKTEST",
        exec_engine=ExecEngineConfig(),
        risk_engine=RiskEngineConfig(bypass=True),
    )
    engine = BacktestEngine(config=engine_config)

    # 3. Adding the IDEALPRO Exchange venue
    IBKR_VENUE = Venue("IDEALPRO")
    engine.add_venue(
        venue=IBKR_VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(100_000, USD)],
    )

    # 4. Strategy configuration and instantiation
    strategy_config = MeanReversionConfig(
        instrument_id=eurusd.id,
        bar_type=eurusd_bar_type,
        bb_period=21,
        bb_deviation=2.0,
        rsi_period=14,
        rsi_overbought=70.0,
        rsi_oversold=30.0,
        er_period=14,
        max_er=0.30,
        trade_size=eurusd.make_qty(100_000),
    )
    strategy = MeanReversionStrategy(config=strategy_config)

    # 5. Configuring the engine
    engine.add_strategy(strategy)
    engine.add_instrument(eurusd)
    engine.add_data(bars)

    # 6. Running the enigne(backtest)
    print("Running backtest...\n")
    engine.run()

    # 7. Generating an HTML Report
    report_path = Path("backtest/backtest_results.html")

    print("Generating an HTML Report...\n")
    create_tearsheet(
        engine=engine,
        output_path=str(report_path),
        currency=USD,
    )

    print(f"DONE! Open this file in your browser: {report_path.resolve()}\n")