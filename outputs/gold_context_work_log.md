# Gold Context Work Log

## 2026-08-23

- Archived old broad-candidate docs and outputs to `archive/legacy_pre_gold_context_20260823_014050/`.
- Preserved source data, transcripts, frames, raw OHLCV data, scripts, and the user's manual workbook.
- Established the new standard: only fully reconstructable trades can become rule evidence.
- Created the new schema and workflow docs.
- Updated the gold definition: fully specified unfilled/canceled actionable setups can also become rule evidence, because Craig's copyable decision ends at the completed setup.

## Immediate Scope

Start from `bDgZhBFm1mU` after 12:20 and proceed toward the newest eligible live-trading videos.

Known caution: the YouTube playlist page currently exposes 38 items on initial HTML load, while local metadata also contains recent live-trading videos such as `-tMUBX41Tqo` and `C3-ZcTx1mpE`. These should be checked as eligible recent live-trading videos even if the initial playlist HTML omits them.

## bDgZhBFm1mU After 12:20 Transcript Pass

Saved transcript-only review rows to `data/processed/gold_context_trades/context_review_queue.csv`.

Summary:

- 8 post-12:20 events were separated.
- 4 actual trade events need frame/recap review before gold promotion.
- 3 pass/missed/no-fill events should not train trade-entry rules, but may later inform no-chase, no-fill, and conditional-pass rules.
- 1 BE event is context incomplete unless frames recover symbol/direction/setup.
- No post-12:20 event was promoted to gold yet, because local bDg frame evidence was not found in `data/source/craig_frames/`.

## bDgZhBFm1mU After 12:20 Visual Pass

Saved browser-captured chart frames to:

`data/source/craig_frames/browser_review/bDgZhBFm1mU_after1220/`

Created representative contact sheets:

- `c01_passed_long_context_contact_sheet.jpg`
- `c02_c03_short_loss_reentry_win_contact_sheet.jpg`
- `c04_c05_later_short_context_contact_sheet.jpg`
- `c07_c08_missed_final_setups_contact_sheet.jpg`

Updated `data/processed/gold_context_trades/context_review_queue.csv` with:

- `visual_review_status`
- `chart_frame_paths`
- `chart_understanding_ko`
- `promoted_rule_evidence_type`
- `remaining_checks_ko`

Review outcome:

- `gold_executed_trade_candidate`: 4
- `gold_actionable_setup_candidate`: 2
- `gold_pass_rule_candidate`: 1
- `not_gold_context_incomplete`: 1

Important method note: future videos should not be exhaustively screenshot. Use transcript first, then capture only the chart moments needed to disambiguate setup geometry, entry box, SL/TP, pass/cancel reason, or recap.

## Pilot 3 Sequential Review

Processed the next three oldest-first videos after `bDgZhBFm1mU`:

- `XlnvwMIRByQ` (2025-02-09)
- `nfRXDRJooyg` (2025-03-02)
- `iYpYWnkUyVI` (2025-03-23)

Saved outputs:

- `data/processed/gold_context_trades/pilot_3_context_review.csv`
- `outputs/pilot_3_context_review_summary.md`
- `data/processed/gold_context_trades/pilot_3_transcript_candidate_windows.md`
- `data/processed/gold_context_trades/pilot_3_transcript_candidate_windows_gap15.md`
- frame folders under `data/source/craig_frames/browser_review/*_pilot3/`

Review outcome:

- 20 decision-unit rows.
- 14 `gold_executed_trade_candidate`.
- 3 `gold_actionable_setup_candidate`.
- 1 `gold_pass_rule_candidate`.
- 2 `context_incomplete_not_gold`.
- 43 selected browser-captured chart frames were used; no exhaustive frame scraping.

Key note: `nfRXDRJooyg` title says 5 trades, but transcript/journal math implies more decision units. The pilot records decision units rather than title count.

## Final Master v0.2 / Time Handling

Generated sequential remaining-video review queue and final integrated master:

- `data/processed/gold_context_trades/remaining_context_queue_v0_2.csv`
- `data/processed/gold_context_trades/remaining_frame_capture_plan_v0_2.csv`
- `data/processed/gold_context_trades/final_context_master_v0_2.csv`
- `data/processed/gold_context_trades/final_gold_ready_candidates_v0_2.csv`
- `outputs/final_context_master_v0_2_summary.md`

Important time rule:

- `market_time_utc_minus4` is reserved for secured actual chart/trade time only: user manual Excel, visible bottom axis, position box, or OHLCV visual alignment.
- Spoken/session clock mentions are not treated as actual trade time. They are stored separately in `market_time_hint_utc_minus4` and should only be used for rough navigation.
- The regenerated master has 15 secured UTC-4 times, all from the user's manual seed rows. Non-manual visual and automatic rows keep secured time blank until bottom-axis/OHLCV alignment is done.

Quality checks:

- master rows: 232
- gold-ready/manual-visual rows: 41
- remaining auto queue rows: 188 across 26 videos
- remaining scope order now runs 15 through 40, with local recent videos `-tMUBX41Tqo` and `C3-ZcTx1mpE` inserted chronologically.
- non-manual rows with secured time: 0
- spoken/session time hints: 74
- rejected hint evidence with money/risk/news/minutes/profit/loss/R-context: 0 in the final validation scan.

## Frame + OHLCV Validated Pass 01

Processed the first remaining video after the pilot set:

- `iGJALewp2dI` / scope 15 / LIVE TRADING CRYPTO - How I Profit $2,963 With Controlled Risk

Outputs:

- `data/processed/gold_context_trades/frame_data_video_session_maps_v0_1.csv`
- `data/processed/gold_context_trades/frame_data_trade_context_queue_v0_1.csv`
- `data/processed/gold_context_trades/frame_data_rule_seed_queue_v0_1.csv`
- `outputs/frame_data_validated_iGJALewp2dI_summary.md`
- Frames: `data/source/craig_frames/browser_review/iGJALewp2dI_frame_data_pass/`

Method update:

- Use logged-in YouTube playback in theater mode.
- Capture only setup/entry/management/recap frames.
- If subtitles obscure position calculator numbers, toggle captions off and recapture only number-sensitive frames.
- Use OHLCV to validate price path, stop/target reach, and approximate UTC-4 windows.
- Do not promote exact minute as high confidence unless the frame has a visible time overlay or strong spoken-time + data alignment.

Result:

- 1 session map row.
- 6 frame+data validated trade context rows.
- 6 rule seed rows.
- 2025-03-27 ETH/SOL/BTC 1m cache was added to validate the next-morning ETH short.

## Frame + OHLCV Validated Pass 02

Processed exactly two additional videos, then stopped:

- `p47HZv1fcUM` / scope 16 / Live Day Trading (I DID NOT EXPECT TO WIN)
- `mNnqjq8BzeA` / scope 17 / Live Day Trading (THIS DAY WAS BORING BUT WORKED)

Outputs:

- `data/processed/gold_context_trades/frame_data_video_session_maps_v0_2.csv`
- `data/processed/gold_context_trades/frame_data_trade_context_queue_v0_2.csv`
- `data/processed/gold_context_trades/frame_data_rule_seed_queue_v0_2.csv`
- `outputs/frame_data_validated_batch_scope16_17_summary.md`
- Frames: `data/source/craig_frames/browser_review/p47HZv1fcUM_frame_data_pass/`
- Frames: `data/source/craig_frames/browser_review/mNnqjq8BzeA_frame_data_pass/`

Result:

- cumulative session map rows: 3
- cumulative frame+data validated trade context rows: 20
- cumulative rule seed rows: 20
- p47 added 6 decision rows.
- mNn added 8 decision rows.
- `2025-05-01` SOLUSDT 1m cache was added to validate the final SOL overnight short near-TP/BE result.

Validation:

- Evidence frame path check: 0 missing paths.
- p47 frame count: 22.
- mNn frame count: 32.
