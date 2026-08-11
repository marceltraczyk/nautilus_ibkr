import sys
sys.path.insert(0, "/home/marce/nautilus_ikbr")

import matplotlib.pyplot as plt
import pandas as pd
from decimal import Decimal
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import ExecEngineConfig, RiskEngineConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.backtest.models import FillModel, MakerTakerFeeModel

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
    print("Running backtest...")
    engine.run()

    # 5. Wyciągnięcie raportów i analiza wyników
    account_report = engine.trader.generate_account_report(IBKR_VENUE)
    positions_report = engine.trader.generate_positions_report()

    # 7. Wyciągnięcie raportów i analiza wyników
    from pathlib import Path

    raw_positions = engine.trader.generate_positions_report()
    positions_df = pd.DataFrame(raw_positions)

    # Nautilus używa nazwy kolumny 'realized_pnl'
    if not positions_df.empty and "realized_pnl" in positions_df.columns:
        # Wyciągamy samą liczbę z tekstu (np. "-62.00 USD" -> -62.00)
        positions_df["pnl"] = (
            positions_df["realized_pnl"]
            .astype(str)
            .str.extract(r"([-+]?\d*\.?\d+)")[0]
            .astype(float)
            .fillna(0)
        )

        total_trades = len(positions_df)
        winning_trades = len(positions_df[positions_df["pnl"] > 0])
        losing_trades = len(positions_df[positions_df["pnl"] < 0])

        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        gross_profit = positions_df[positions_df["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(positions_df[positions_df["pnl"] < 0]["pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        total_pnl = positions_df["pnl"].sum()

        print("\n" + "=" * 50)
        print("           KLUCZOWE WSKAŹNIKI STRATEGII          ")
        print("=" * 50)
        print(f"Całkowity PnL:             {total_pnl:.2f} USD")
        print(f"Liczba transakcji:         {total_trades}")
        print(f"Wygrane / Stratne:         {winning_trades} / {losing_trades}")
        print(f"Win Rate:                  {win_rate:.2f}%")
        print(f"Profit Factor:             {profit_factor:.2f}")
        print(f"Średni zysk/strata na trade: {total_pnl / total_trades:.2f} USD")
        print("=" * 50 + "\n")

        # Wykres krzywej kapitału (Equity Curve)
        positions_df["cumulative_pnl"] = positions_df["pnl"].cumsum() + 100_000
        plt.figure(figsize=(12, 6))
        plt.plot(positions_df["cumulative_pnl"], label="Equity Curve (USD)", color="#1f77b4")
        plt.title("Krzywa Kapitału - Mean Reversion 2025")
        plt.xlabel("Liczba transakcji")
        plt.ylabel("Kapitał (USD)")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()

        # Zapis bezpośrednio do katalogu, w którym znajduje się skrypt
        script_dir = Path(__file__).parent
        chart_path = script_dir / "equity_curve.png"
        plt.savefig(chart_path)
        print(f"--> Wykres zapisan do: {chart_path.resolve()}")
    else:
        print("--> Brak zamkniętych pozycji w podanym okresie.")