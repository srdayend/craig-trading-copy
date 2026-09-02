# Script Index

The scripts are grouped by the workflow stage they support.

## Source And Context Extraction

- `build_gold_context_seed.py`: converts the manual workbook into initial gold-context seed rows.
- `build_craig_manual_gold_seed.py`: builds manual seed context records.
- `extract_pilot_context_windows.py`: extracts transcript windows for pilot review.
- `build_pilot3_context_review.py`: builds the pilot-3 context review table.
- `print_transcript_range.py`, `print_srt_keyword_windows.py`, `print_v03_batch_candidates.py`: small inspection helpers.

## Gold-Context Queues

- `build_v03_gold_context_queues.py`: creates v0.3 gold-context queues.
- `build_v03_batch_01_queues.py`, `build_v03_batch_02_queues.py`, `build_v03_batch_03_queues.py`: batch queue builders.
- `build_remaining_context_queue_v0_2.py`: review queue for remaining candidate windows.
- `build_final_context_master_v0_2.py`: combines reviewed and queued context rows.
- `audit_v03_non_gold_candidates.py`: audits candidates that should not become gold evidence.

## Evidence Frames And Workbooks

- `extract_v03_batch_frames.py`, `extract_v03_upgrade_frames.py`: frame extraction helpers.
- `build_frame_contact_sheets.py`: creates contact sheets for frame review.
- `detect_position_box_from_frame.py`: detects position-box candidates in frames.
- `build_quality_status_inputs.py`: prepares tracker input data.
- `build_quality_tracker_workbook.mjs`: builds the quality tracker workbook.
- `prepare_craig_v1_2_manual_review_workbook_data.py`: prepares manual review workbook rows.
- `build_craig_v1_2_manual_review_workbook.mjs`: builds the manual chart review workbook.

## Market Data And Feature Generation

- `fetch_live_date_ohlcv.py`: fetches live-date OHLCV windows.
- `fetch_craig_v1_2_binance_continuous_ohlcv.py`: fetches continuous Binance futures OHLCV data.
- `summarize_ohlcv_windows.py`, `print_ohlcv_slice.py`: OHLCV inspection helpers.
- `build_craig_v1_features.py`: builds the v1 feature matrix.
- `build_craig_v1_2_market_features.py`: builds v1.2 market feature snapshots.
- `build_craig_v1_2_btc_context.py`: builds BTC context snapshots.
- `build_craig_v1_2_htf_zones.py`: builds higher-timeframe zones and trendline context.

## Rule Replay And Strategy Research

- `run_craig_v1_decision_replay.py`: replays Craig-style decisions from v1 features.
- `run_craig_v1_1_mismatch_calibration.py`: calibrates mismatch-driven v1.1 rules.
- `run_craig_v1_2_event_driven_execution.py`: runs v1.2 event-driven fill/stop/target simulation.
- `run_sol_craig_rule_backtest.py`: legacy SOL rule-backtest prototype.
- `craig_emulator_reference.py`: reference emulator for Craig-style state-machine logic.
- `analyze_sol_backtest_sensitivity.py`: sensitivity analysis helper.

## Candidate Builders And Audits

- `build_v1_decision_units.py`: normalizes gold context into decision units.
- `build_craig_intent_entry_answer_key.py`: builds intent/entry answer-key data.
- `build_craig_v1_2_trade_candidates.py`: builds v1.2 trade candidates.
- `build_craig_v1_2_sniper_trade_candidates.py`: filters S/A-tier sniper candidates.
- `build_craig_v1_2_scenario_thesis.py`: scores scenario thesis context.
- `build_craig_v1_2_target_pools.py`: builds structural target pools.
- `build_craig_v1_2_thesis_snapshots.py`: builds thesis snapshots.
- `build_craig_similarity_mismatch_audit.py`: audits similarity and mismatch behavior.
- `build_craig_trade_context_review.py`: builds review tables for trade context.
- `build_craig_live_inventory.py`: inventories available live-trading sources.
- `build_craig_all_trade_candidate_queue.py`, `build_craig_expanded_trade_episode_bank.py`, `build_craig_gold_episode_candidate_bank.py`: candidate and episode-bank builders.
- `build_external_chart_tool_probe.py`, `external_chart_tools.py`: evaluates external chart-pattern helper options.
- `sync_obsidian_direction_overrides.py`: syncs local Obsidian direction override notes.
