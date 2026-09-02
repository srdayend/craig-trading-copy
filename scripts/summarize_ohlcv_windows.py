from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def parse_window(raw: str, date: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = raw.split("-", 1)
    tz = "Etc/GMT+4"
    return pd.Timestamp(f"{date} {start}", tz=tz), pd.Timestamp(f"{date} {end}", tz=tz)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("date")
    parser.add_argument("symbol")
    parser.add_argument("windows", nargs="+")
    args = parser.parse_args()

    path = (
        ROOT
        / "data/raw/binance_futures_live_dates"
        / args.date
        / f"{args.symbol}_1m_{args.date}_ny.csv"
    )
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["ny"] = df["timestamp"].dt.tz_convert("Etc/GMT+4")
    df["range"] = df["high"] - df["low"]

    print(f"{args.date} {args.symbol} rows={len(df)}")
    for raw in args.windows:
        start, end = parse_window(raw, args.date)
        window = df[(df["ny"] >= start) & (df["ny"] <= end)]
        if window.empty:
            print(f"{raw}: no rows")
            continue
        high = window.loc[window["high"].idxmax()]
        low = window.loc[window["low"].idxmin()]
        print(
            f"{raw}: open {window['open'].iloc[0]:.2f} close {window['close'].iloc[-1]:.2f} "
            f"high {high['high']:.2f}@{high['ny'].strftime('%H:%M')} "
            f"low {low['low']:.2f}@{low['ny'].strftime('%H:%M')}"
        )
        top = []
        for _, row in window.nlargest(3, "range").iterrows():
            top.append(
                f"{row['ny'].strftime('%H:%M')} "
                f"O{row['open']:.2f} H{row['high']:.2f} L{row['low']:.2f} C{row['close']:.2f}"
            )
        print("  top_ranges: " + "; ".join(top))


if __name__ == "__main__":
    main()
