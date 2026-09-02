# Frame + Data Validated Context: iGJALewp2dI

첫 남은 영상에 대해 로그인된 YouTube 프레임과 Binance 1m 데이터를 함께 사용해 문맥 큐를 만들었다.

## Outputs

- session map: `data/processed/gold_context_trades/frame_data_video_session_maps_v0_1.csv`
- trade context queue: `data/processed/gold_context_trades/frame_data_trade_context_queue_v0_1.csv`
- rule seed queue: `data/processed/gold_context_trades/frame_data_rule_seed_queue_v0_1.csv`
- frame folder: `data/source/craig_frames/browser_review/iGJALewp2dI_frame_data_pass`

## Counts

- sessions: 1
- trades/decision units: 6
- rule seeds: 6

## Method

- YouTube frame capture: setup/entry/management/recap only, not exhaustive scraping.
- Visual anchors: symbol, timeframe, position box entry/SL/TP, time overlays, recap journal.
- Data anchors: SOLUSDT 2025-03-26 1m; ETHUSDT 2025-03-27 1m.
- Gold rule principle: rows are usable for rule extraction, but exact minute fields remain `medium` unless directly visible or strongly aligned.
