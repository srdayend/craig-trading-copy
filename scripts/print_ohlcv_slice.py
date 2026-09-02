from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("date")
    parser.add_argument("symbol")
    parser.add_argument("start_hhmm")
    parser.add_argument("end_hhmm")
    parser.add_argument("--touch", type=float, nargs="*")
    parser.add_argument("--near-close", type=float, nargs="*")
    parser.add_argument("--near-width", type=float, default=0.08)
    args = parser.parse_args()

    path = (
        ROOT
        / "data/raw/binance_futures_live_dates"
        / args.date
        / f"{args.symbol}_1m_{args.date}_ny.csv"
    )
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["ny"] = df["timestamp"].dt.tz_convert("Etc/GMT+4")
    start = pd.Timestamp(f"{args.date} {args.start_hhmm}", tz="Etc/GMT+4")
    end = pd.Timestamp(f"{args.date} {args.end_hhmm}", tz="Etc/GMT+4")
    window = df[(df["ny"] >= start) & (df["ny"] <= end)]

    for _, row in window.iterrows():
        include = not args.touch and not args.near_close
        for price in args.touch or []:
            if row["low"] <= price <= row["high"]:
                include = True
        for price in args.near_close or []:
            if abs(row["close"] - price) <= args.near_width:
                include = True
        if include:
            print(
                f"{row['ny'].strftime('%H:%M')} "
                f"O{row['open']:.2f} H{row['high']:.2f} L{row['low']:.2f} C{row['close']:.2f}"
            )


if __name__ == "__main__":
    main()
