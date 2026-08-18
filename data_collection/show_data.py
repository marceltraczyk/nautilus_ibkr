"""Show what is stored in the Parquet catalog written by download_data.py.

    show_data.py           # summary of every bar type
    show_data.py EURUSD    # file-by-file detail + gaps
"""

import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


CATALOG_PATH = Path(__file__).parent / "parquet_data"

BARS_PER_DAY = 96  # 24h of 15-minute bars
GAPS_TO_SHOW = 10
WEEKEND_HOURS = 47.0  # A normal FX weekend close


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def bar_type_dirs(catalog_path: Path) -> list[Path]:
    bar_root = catalog_path / "data" / "bar"
    if not bar_root.exists():
        return []

    return sorted(path for path in bar_root.iterdir() if path.is_dir())


def read_timestamps(files: list[Path]) -> pd.DatetimeIndex:
    """Read just the ts_init column across a bar type's files, in order."""
    stamps: list[int] = []
    for file in files:
        stamps.extend(pq.read_table(file, columns=["ts_init"])["ts_init"].to_pylist())

    return pd.to_datetime(sorted(stamps), unit="ns", utc=True)


def instrument_ids(catalog_path: Path) -> list[str]:
    instrument_root = catalog_path / "data" / "currency_pair"
    if not instrument_root.exists():
        return []

    return sorted(path.name for path in instrument_root.iterdir() if path.is_dir())


def summarise(catalog_path: Path) -> None:
    directories = bar_type_dirs(catalog_path)
    instruments = instrument_ids(catalog_path)

    print(f"Catalog:     {catalog_path}")
    print(f"Instruments: {len(instruments)}   bar types: {len(directories)}\n")

    header = f"{'BAR TYPE':<44}{'BARS':>12}  {'FROM':<12}{'TO':<12}{'FILES':>6}{'SIZE':>10}{'COVER':>8}"
    print(header)
    print("-" * len(header))

    total_bars = 0
    total_files = 0
    total_size = 0.0

    for directory in directories:
        files = sorted(directory.glob("*.parquet"))
        if not files:
            continue

        bars = sum(pq.ParquetFile(file).metadata.num_rows for file in files)
        size = sum(file.stat().st_size for file in files)
        stamps = read_timestamps(files)

        first, last = stamps[0], stamps[-1]

        # Holidays are not excluded, so a healthy catalog lands just under 100%
        weekdays = len(pd.bdate_range(first.date(), last.date()))
        cover = bars / (weekdays * BARS_PER_DAY) * 100 if weekdays else 0.0

        print(
            f"{directory.name:<44}{bars:>12,}  "
            f"{first.date().isoformat():<12}{last.date().isoformat():<12}"
            f"{len(files):>6}{human_size(size):>10}{cover:>7.0f}%"
        )

        total_bars += bars
        total_files += len(files)
        total_size += size

    print("-" * len(header))
    print(f"{'TOTAL':<44}{total_bars:>12,}  {'':<24}{total_files:>6}{human_size(total_size):>10}")


def detail(catalog_path: Path, needle: str) -> None:
    matches = [d for d in bar_type_dirs(catalog_path) if needle.upper() in d.name.upper()]

    if not matches:
        print(f"No bar type matching '{needle}'. Run without arguments to list them all.")
        return

    for directory in matches:
        files = sorted(directory.glob("*.parquet"))
        print(f"\n{directory.name}   ({len(files)} files)")
        print(f"  {'#':>3}{'BARS':>12}  {'FROM':<18}{'TO':<18}{'SIZE':>10}")
        print("  " + "-" * 62)

        for number, file in enumerate(files, start=1):
            stamps = read_timestamps([file])
            print(
                f"  {number:>3}{len(stamps):>12,}  "
                f"{stamps[0].strftime('%Y-%m-%d %H:%M'):<18}"
                f"{stamps[-1].strftime('%Y-%m-%d %H:%M'):<18}"
                f"{human_size(file.stat().st_size):>10}"
            )

        stamps = read_timestamps(files)
        deltas = stamps.to_series().diff().dropna()
        gaps = deltas[deltas > pd.Timedelta(hours=1)]

        # A weekly close is expected, anything else is a real hole
        hours = gaps.dt.total_seconds() / 3600
        weekends = gaps[(hours - WEEKEND_HOURS).abs() < 4]
        holes = gaps.drop(weekends.index).sort_values(ascending=False)

        print(f"\n  Missing periods (excluding {len(weekends)} normal weekend closes):")

        if holes.empty:
            print("    none - the series is continuous apart from weekends")
            continue

        for end, delta in holes.head(GAPS_TO_SHOW).items():
            start = end - delta
            print(
                f"    {delta.total_seconds() / 3600:>7.1f}h   "
                f"{start.strftime('%Y-%m-%d %H:%M')} -> {end.strftime('%Y-%m-%d %H:%M')}"
            )

        if len(holes) > GAPS_TO_SHOW:
            print(f"    ... and {len(holes) - GAPS_TO_SHOW} more")


def main() -> None:
    if not CATALOG_PATH.exists():
        print(f"No catalog at {CATALOG_PATH}")
        print("Run download_data.py first.")
        sys.exit(1)

    if len(sys.argv) > 1:
        detail(CATALOG_PATH, sys.argv[1])
    else:
        summarise(CATALOG_PATH)


if __name__ == "__main__":
    main()
