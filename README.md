# nautilus_ibkr

An FX trading setup built on [NautilusTrader](https://nautilustrader.io) and the
Interactive Brokers API. It downloads historical bars, backtests a mean reversion
strategy on them, and runs the same strategy live against an IBKR paper account.

## Layout

| Folder | What it does |
|---|---|
| `data_collection/` | Downloads 15-minute FX bars from IBKR into a Parquet catalog |
| `backtest/` | Runs the strategy over the downloaded history and writes an HTML report |
| `src/` | Runs the strategy live against a paper account |

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- An IBKR account with paper trading enabled
- Docker, only for the containerised gateway

## Setup

```bash
git clone https://github.com/marceltraczyk/nautilus_ibkr.git
cd nautilus_ibkr
uv sync
cp .env.example .env
```

Then fill in your IBKR credentials in `.env`.

## Downloading data

```bash
uv run data_collection/download_data.py
```

Fetches 10 years of 15-minute mid-price bars for 20 FX pairs into
`data_collection/parquet_data/` — around 4.9 million bars and 200 MB.

IBKR caps historical requests at 60 per 10 minutes, so a full download takes a few
hours. It is resumable: interrupt it whenever, and the next run skips what is
already stored and picks up where it stopped.

Pairs covered:

```
EUR/USD  USD/JPY  GBP/USD  USD/CHF  AUD/USD  USD/CAD  NZD/USD
EUR/JPY  EUR/GBP  EUR/CHF  EUR/AUD  EUR/CAD  GBP/JPY  GBP/CHF
GBP/AUD  AUD/JPY  CAD/JPY  CHF/JPY  NZD/JPY  AUD/NZD
```

### Inspecting the catalog

```bash
uv run data_collection/show_data.py
```

```
BAR TYPE                                            BARS  FROM        TO           FILES      SIZE   COVER
AUDJPY.IDEALPRO-15-MINUTE-MID-EXTERNAL           246,247  2016-08-14  2026-08-18      41   10.1 MB     98%
AUDNZD.IDEALPRO-15-MINUTE-MID-EXTERNAL           246,188  2016-08-14  2026-08-18      41    9.3 MB     98%
AUDUSD.IDEALPRO-15-MINUTE-MID-EXTERNAL           246,247  2016-08-14  2026-08-18      41    9.3 MB     98%
...
TOTAL                                          4,924,763                             820  198.5 MB
```

`COVER` is how much of a full trading calendar the data actually fills. Around 98%
is healthy — the missing slice is bank holidays, when the market is closed. A
clearly lower number points at real gaps.

Pass a pair name for a file-by-file breakdown and the largest missing periods:

```bash
uv run data_collection/show_data.py EURUSD
```

```
Missing periods (excluding 510 normal weekend closes):
      75.2h   2023-12-22 21:00 -> 2023-12-26 00:15
      74.2h   2022-12-30 22:00 -> 2023-01-03 00:15
      51.2h   2023-04-07 21:00 -> 2023-04-10 00:15
```

## Backtesting

```bash
uv run backtest/backtest_strategy.py
```

Runs the strategy over the downloaded bars and writes `backtest/backtest_results.html`
— an interactive tearsheet with the equity curve, drawdowns, Sharpe and Sortino
ratios, win rate and profit factor.

## Live trading

Both entry points trade the same strategy on a paper account. Pick the one that
matches how you run the gateway.

Start IB Gateway yourself, log in and enable the API socket:

```bash
uv run src/main.py
```

Or let the script start a gateway container and stop it on exit:

```bash
uv run src/main_docker_gateway.py
```

The strategy logs a line per bar, so you can watch it warm up and then track how
close price sits to each threshold:

```
Warming up: 14/21 bars | close 1.11593
[FLAT] close 1.11546 | bands 1.11532 / 1.11610 / 1.11689 | RSI 0.33 (buy <0.30, sell >0.70) | ER 0.16 (trade <0.30)
SELL signal! Close: 1.13034 > Upper: 1.12895 | RSI: 0.76 | ER: 0.30
Take Profit for SHORT! Price 1.13009 reached 1.13016
```

Stop either entry point with `Ctrl+C`.

## The strategy

`src/mean_reversion.py` — enters when price leaves a Bollinger band with RSI at an
extreme, and only while the Kaufman Efficiency Ratio says the market is choppy
rather than trending. Exits at the middle band.

Paper trading only. It has no stop loss and is not meant for real money.

## Configuration

`src/config.py` drives live trading:

```python
INSTRUMENT_ID = "EUR/USD.IDEALPRO"
BAR_TYPE = f"{INSTRUMENT_ID}-1-MINUTE-MID-EXTERNAL"
TRADE_SIZE = 100_000
```

Live runs on 1-minute bars so the indicators warm up in about 20 minutes rather
than five hours. Switch `BAR_TYPE` to `15-MINUTE` to match the backtest.

Bar size, date range and the pair list sit at the top of
`data_collection/download_data.py`. Strategy thresholds live in
`MeanReversionConfig` in `src/mean_reversion.py`.

## Notes

**Read-only API.** When you run IB Gateway yourself, turn off *Read-Only API* in
its API settings. Leave it on and market data still flows, but every order is
rejected.

**Gateway on Windows, code in WSL.** `127.0.0.1` from WSL does not reach the
Windows host. Set `IB_HOST` in `.env` to the address from `ip route | grep default`.
