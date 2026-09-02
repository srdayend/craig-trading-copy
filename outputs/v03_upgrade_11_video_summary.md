# v0.3 Upgrade Summary - 11 Videos

## Scope Completed

Upgraded and integrated 11 videos before processing any new videos:

- 5 manual seed videos upgraded with local mp4/SRT frames.
- 3 pilot3 videos promoted into the v0.3 schema.
- 3 frame-data v0.2 videos schema-upgraded with macro/scenario/symbol/wave/live-thesis fields separated.

## Output Queues

- `data/processed/gold_context_trades/gold_v03_video_session_maps.csv`
- `data/processed/gold_context_trades/gold_v03_trade_context_queue.csv`
- `data/processed/gold_context_trades/gold_v03_all_context_queue.csv`
- `data/processed/gold_context_trades/gold_v03_hold_context_queue.csv`
- `data/processed/gold_context_trades/gold_v03_rule_seed_queue.csv`
- `data/processed/gold_context_trades/gold_v03_quality_audit.csv`

## Counts

- Sessions: 11
- All decision contexts: 64
- Gold-ready decision contexts: 62
- Hold/context-incomplete rows: 2
- Rule seed rows: 62

## Important Quality Decision

The 2 originally incomplete pilot3 rows were not forced into the gold-ready queue. They remain in `gold_v03_hold_context_queue.csv` and `gold_v03_all_context_queue.csv`, but are excluded from `gold_v03_trade_context_queue.csv` and `gold_v03_rule_seed_queue.csv`.

## v0.3 Additions

- Session macro/HFT context separated.
- Scenario tree separated.
- Symbol-selection context separated.
- Elliott/Fib/wave context separated.
- Live thesis changes separated.
- Visible chart time note added to avoid confusing visible TradingView timezone, such as UTC-7, with required UTC-4 alignment.
- Local video frame evidence attached for manual and pilot upgrades.

## Progress Tracker

The workbook at `outputs/craig_quality_tracker_v0_3/craig_video_quality_tracker_v0_3.xlsx` now shows:

- Q4 v0.3 gold-ready integrated: 11
- Q0 auto transcript queue remaining: 21
