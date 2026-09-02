# Frame + Data Validated Batch: Scope 16-17

Processed exactly two additional videos after the first frame+data pass.

## Videos

- `p47HZv1fcUM` / scope 16 / `Live Day Trading (I DID NOT EXPECT TO WIN)` / 6 decision rows
- `mNnqjq8BzeA` / scope 17 / `Live Day Trading (THIS DAY WAS BORING BUT WORKED)` / 8 decision rows

## Outputs

- session map: `data/processed/gold_context_trades/frame_data_video_session_maps_v0_2.csv`
- trade context queue: `data/processed/gold_context_trades/frame_data_trade_context_queue_v0_2.csv`
- rule seed queue: `data/processed/gold_context_trades/frame_data_rule_seed_queue_v0_2.csv`
- p47 frames: `data/source/craig_frames/browser_review/p47HZv1fcUM_frame_data_pass/`
- mNn frames: `data/source/craig_frames/browser_review/mNnqjq8BzeA_frame_data_pass/`

## Cumulative Counts

- sessions: 3
- trade/decision contexts: 20
- rule seeds: 20

## Method Notes

- Captured selected setup/entry/management/recap frames from logged-in YouTube playback.
- Used visible overlays and TradingView symbols/timeframes to confirm chart context.
- Used Binance 1m NY-session OHLCV for 2025-04-09 SOL, 2025-04-30 SOL/ETH, and 2025-05-01 SOL overnight validation.
- Rows with exact price not safely OCR-readable keep `about` values and explain uncertainty.
