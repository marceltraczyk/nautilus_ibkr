import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nautilus_trader.analysis import create_tearsheet
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FillModel, FixedFeeModel
from nautilus_trader.config import ExecEngineConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from src.mean_reversion import MeanReversionConfig, MeanReversionStrategy

if __name__ == "__main__":
    # 1. Load the instrument and its bars from the catalog
    CATALOG_PATH = Path(__file__).resolve().parent.parent / "data_collection" / "parquet_data"

    catalog = ParquetDataCatalog(CATALOG_PATH)

    instruments = catalog.instruments()
    eurusd = instruments[0]

    bars = catalog.bars(instrument_ids=[eurusd.id])
    eurusd_bar_type = bars[0].bar_type

    print(f"Detected instrument: {eurusd.id}")
    print(f"Detected bar type: {eurusd_bar_type}")
    print(f"Number of bars loaded into memory: {len(bars)}")

    # 2. Engine
    engine_config = BacktestEngineConfig(
        trader_id="IBKR-BACKTEST",
        exec_engine=ExecEngineConfig(),
        risk_engine=RiskEngineConfig(bypass=True),  # Revisit before live trading
    )
    engine = BacktestEngine(config=engine_config)

    # 3. Venue
    IBKR_VENUE = Venue("IDEALPRO")
    engine.add_venue(
        venue=IBKR_VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(100_000, USD)],
        fee_model=FixedFeeModel(Money(4.5, USD)),  # IBKR commission + half the typical spread
        fill_model=FillModel(prob_slippage=0.3, random_seed=42),  # Illustrative - tune via sensitivity testing
    )

    # 4. Strategy
    strategy_config = MeanReversionConfig(
        instrument_id=eurusd.id,
        bar_type=eurusd_bar_type,
        trade_size=eurusd.make_qty(100_000),
    )
    strategy = MeanReversionStrategy(config=strategy_config)

    # 5. Wire it together
    engine.add_strategy(strategy)
    engine.add_instrument(eurusd)
    engine.add_data(bars)

    # 6. Run
    print("Running backtest...\n")
    engine.run()

    # 7. HTML report
    report_path = Path(__file__).resolve().parent / "backtest_results.html"

    print("Generating an HTML Report...\n")
    create_tearsheet(
        engine=engine,
        output_path=str(report_path),
        currency=USD,
    )

    print(f"DONE! Open this file in your browser: {report_path.resolve()}\n")
