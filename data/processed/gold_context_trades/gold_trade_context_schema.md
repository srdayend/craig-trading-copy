# Gold Trade Context Schema

Use this schema for every trade that may become model evidence.

| Column | Description |
|---|---|
| `trade_id` | Stable id: `videoid_tradeNN_timestamp`. |
| `status` | `gold_executed_trade`, `gold_actionable_setup`, `gold_pass_rule`, `needs_frame_review`, `needs_recap_match`, `context_incomplete`, `pass_or_missed`, or `discard`. |
| `source_kind` | `manual_seed`, `transcript_review`, `frame_review`, or `recap_match`. |
| `video_id` | YouTube video id. |
| `video_url` | YouTube link. |
| `playlist_index_oldest_first` | Playlist index if known in oldest-to-newest order. |
| `youtube_anchor` | Main timestamp for setup or entry. |
| `market_time_note` | Market time/date note, including uncertainty. |
| `market_date` | Market date when verified. |
| `market_time_utc_minus4` | Actual chart/trade time in UTC-4/NY market time when extracted. Leave blank if not secured. |
| `market_datetime_utc_minus4` | Combined `market_date` + `market_time_utc_minus4` only when both are secured. |
| `market_time_hint_utc_minus4` | Non-authoritative spoken/session time hint. Do not use for candle alignment without review. |
| `market_datetime_hint_utc_minus4` | Combined `market_date` + `market_time_hint_utc_minus4` for rough navigation only. |
| `market_time_hint_source` | Source of the hint, usually `spoken_time_anchor_unverified`. |
| `market_time_hint_confidence` | `medium`, `low`, or blank. This is separate from secured `market_time_confidence`. |
| `market_time_source` | `user_manual_excel`, `tradingview_bottom_axis`, `ohlcv_visual_alignment`, `upload_proxy_date_only`, or `not_extracted`. Spoken-only time anchors belong in the hint fields. |
| `market_time_confidence` | `high`, `medium`, `low`, or `not_available`. Use `high` only for visible bottom axis/manual verification. |
| `market_time_evidence_ko` | Why this date/time was accepted or why it remains unresolved. |
| `ohlcv_alignment_status` | Whether cached 1m data exists and whether the row has been aligned to actual candles. |
| `symbol` | Trading symbol. |
| `direction` | `long`, `short`, or `unknown_until_frame_review`. |
| `trade_sequence` | Craig trade number or local sequence in the video. |
| `pre_entry_thesis_ko` | Macro/session/HTF thesis before the trade. |
| `intention_timeline_ko` | Craig's evolving intentions, waits, skips, cancels, retries, caution, pair changes. |
| `setup_structure_ko` | Concrete setup: zone, FVG, CHoCH, trendline, SR flip, fib/wave, pair comparison. |
| `entry_plan_ko` | Planned entry logic and trigger. |
| `stop_plan_ko` | Stop placement and reason. |
| `target_plan_ko` | TP or target zone and reason. |
| `execution_ko` | Filled, partial, missed, canceled, no trigger, or re-entered. |
| `management_ko` | BE, risk reduction, trailing, manual adjustment. Required for executed trades only. |
| `result_ko` | Final outcome and how it ended. For unfilled setups, record no-fill/cancel/runaway result. |
| `source_anchors_ko` | Timestamp and frame anchors used for verification. |
| `missing_or_uncertain_ko` | Anything still missing. Empty only for gold rows. |
| `rule_features_ko` | Rule-building features extracted from the trade. |
| `original_notes_ko` | Raw user/manual notes or transcript excerpt summary. |
