# Craig v1.2 DNA-Locked Architecture Refinement v1

This refinement extends `outputs/craig_v1_2_dna_locked_backtest_architecture.md`.

The purpose is not to turn Craig into a generic HTF/FVG quant strategy. The purpose is to preserve the Craig DNA: read the big map, wait for price to reach a meaningful location, risk small near invalidation, and hold for structural high-R targets when the thesis deserves it.

## Source Notes Reviewed

Reviewed local artifacts:

- `outputs/craig_v1_2_dna_locked_backtest_architecture.md`
- `outputs/gold_v03_craig_rule_model_v1_design.md`
- `outputs/gold_context_work_log.md`
- `outputs/gold_v03_decision_units_v1.csv`
- `data/processed/gold_context_trades/context_review_queue.csv`
- `data/processed/gold_context_trades/gold_v03_batch_02_rule_seed_queue.csv`
- `data/processed/gold_context_trades/gold_v03_batch_03_rule_seed_queue.csv`
- `outputs/craig_v1_1_rulebook.yaml`
- `outputs/craig_v1_1_validation_report.md`

Repeated Craig observations from the artifacts:

- FVG midpoint, SR flip, trendline/channel retest, sweep, and CHoCH/BOS repeatedly appear together.
- BTC is a context engine for SOL/ETH, not just a green/red filter.
- Trendline touch, sweep, fakeout, break, and underside/overside retest are recurring PA-zone logic.
- Craig often targets structural locations: 15m/HTF FVG, support/resistance, previous day or current day high/low, lower FVG/key level, PDH/PDL, and next liquidity.
- Craig can all-out at a meaningful nearby target when confidence is lower, opposite trend is strong, BTC context warns, or support/resistance starts holding.
- Runner is earned by structure. It is not always-on, and it is not disabled simply because TP1 exists.

## Refinement Summary

v1.2 should add two locked subsystems:

1. HTF Trendline + BTC PA Context
   - Treat 4h/1h/15m trendlines as PA-zone generators alongside FVG, SR, and liquidity.
   - Interpret BTC by its own HTF PA-zone location and reaction, then apply that to alt confidence, direction permission, warning, or veto.

2. Structural Target Pool + Runner Permission
   - Build TP candidates from known 15m/1h/4h zones before using fixed R.
   - Keep fixed R as a normalization fallback, not the main reason for exit.
   - Separate all-out exit, partial-plus-runner, and no-runner states using confidence and opposing context.

## HTF / 15m Thesis Generator Refinement

### Required PA Inputs

The thesis generator must include:

- SR zones on 15m/1h/4h.
- FVG zones on 15m/1h/4h, including freshness and midpoint.
- Liquidity pools: equal highs/lows, day high/low, previous day high/low, range extremes.
- Trendlines on 4h, 1h, and 15m.
- BTC HTF zone and BTC trendline interaction.
- 1m trigger state only after HTF/15m location is valid.

### Trendline Model

Trendlines are PA zones, not decorative context.

Build swing-based trendlines using completed candles only:

- `htf_trendline_4h`
- `htf_trendline_1h`
- `htf_trendline_15m`

Each trendline object should store:

- `timeframe`
- `line_side`: support, resistance, channel_top, channel_bottom, midline
- `anchor_count`
- `anchor_times`
- `anchor_prices`
- `slope`
- `intercept`
- `projected_price_at_decision`
- `distance_atr`
- `distance_pct`
- `line_quality_score`
- `available_at`
- `invalidated_at`

Detection principles:

- Use only confirmed swing pivots whose candles closed before decision time.
- Require at least two anchors; prefer three or more touches for high confidence.
- Penalize steep, single-contact, or freshly redrawn lines unless retest behavior confirms them.
- Treat manual/frame-derived trendline evidence as higher confidence than purely heuristic OHLCV lines, but never use future anchors.

### Trendline Interaction Type

Add:

- `trendline_interaction_type`

Allowed values:

- `near_touch`: price is within a configured ATR or zone-width threshold of the projected trendline.
- `sweep`: wick pierces the line or line-zone, then closes back on the original side.
- `break_retest`: price closes through the line, then retests it from the opposite side.
- `rejection`: price touches or nearly touches the line and displaces away with 1m/5m confirmation.
- `clean_break`: price closes through the line with displacement and no immediate reclaim.
- `none`: no relevant interaction.

Add:

- `trendline_pa_zone_score`

Score components:

- + for 4h/1h line confluence with 15m SR/FVG/liquidity.
- + for sweep/rejection/break-retest at the line.
- + for line touch occurring at range extreme or day high/low.
- + for BTC confirming at its own PA zone.
- - for middle-of-range touches with no liquidity event.
- - for trendline interaction that already happened and price has moved away, creating chase risk.

### Thesis Fields To Add

Add these to the thesis snapshot:

- `htf_trendline_4h`
- `htf_trendline_1h`
- `htf_trendline_15m`
- `trendline_interaction_type`
- `trendline_pa_zone_score`
- `trendline_zone_confluence_count`
- `trendline_near_touch_distance_atr`
- `trendline_break_retest_valid`
- `trendline_sweep_valid`
- `trendline_rejection_confirmed`
- `sr_zone_score`
- `sr_trendline_overlap`
- `fvg_trendline_overlap`
- `liquidity_trendline_overlap`

Hard reject additions:

- Reject 1m trigger if no HTF/15m PA zone exists and trendline score is weak.
- Reject trendline-only trades if the line has low anchor quality and no SR/FVG/liquidity overlap.
- Reject if the best trendline touch happened before the signal and the entry would be a chase.
- Reject if `trendline_interaction_type=clean_break` against the intended direction and no retest/reclaim has happened.

## BTC PA Context For Alt Trades

BTC should be interpreted as a market-state map. Do not reduce it to simple return or candle color.

### BTC Fields To Add

Add:

- `btc_htf_zone_kind`
- `btc_trendline_interaction_type`
- `btc_pa_reaction_state`
- `btc_leader_context_score`
- `btc_context_effect`

Allowed `btc_htf_zone_kind`:

- `4h_trendline`
- `1h_trendline`
- `15m_trendline`
- `4h_sr_zone`
- `1h_sr_zone`
- `15m_sr_zone`
- `4h_fvg`
- `1h_fvg`
- `15m_fvg`
- `liquidity_pool`
- `day_high_low`
- `previous_day_high_low`
- `none`

Allowed `btc_trendline_interaction_type`:

- `near_touch`
- `sweep`
- `break_retest`
- `rejection`
- `clean_break`
- `none`

Allowed `btc_pa_reaction_state`:

- `bullish_rejection`
- `bearish_rejection`
- `bullish_acceptance`
- `bearish_acceptance`
- `chop_no_decision`
- `liquidity_sweep_reclaim`
- `liquidity_sweep_fail`
- `none`

Allowed `btc_context_effect`:

- `confirm`: BTC PA-zone location and reaction supports the alt thesis.
- `warn`: BTC is at a conflicting zone or has weak/choppy confirmation; reduce confidence or runner permission.
- `veto`: BTC strongly rejects against the alt direction or clean-breaks a critical level against the thesis.
- `neutral`: no actionable BTC PA-zone context.

### BTC Context Logic

For SOL/ETH trades:

- If BTC is rejecting from an HTF resistance/trendline while an alt long is late into resistance, set `btc_context_effect=warn` or `veto`.
- If BTC sweeps/reclaims HTF support and alt offers a 15m/FVG/SR long setup, set `confirm`.
- If BTC clean-breaks a major trendline/SR against the alt thesis, set `veto` unless the alt has an independent reversal-at-extreme with very strong local evidence.
- If BTC is chopping in the middle of its range, set `neutral` and avoid over-weighting BTC.
- If BTC is near a major trendline but has not reacted, set `warn` rather than `confirm`.

BTC should affect:

- `thesis_score`
- `thesis_side_permission`
- `trade_confidence_score`
- `runner_hold_permission`
- `all_out_exit_allowed`
- `position_size_modifier`

BTC must not:

- Directly copy BTC direction into the alt side.
- Override a clean alt reversal without a BTC PA-zone reason.
- Use future BTC reaction after the alt decision timestamp.

## Mode Refinement

Headline reversal variants:

- `R1_reversal_extreme_sr_fvg`: HTF range extreme plus SR/FVG reaction.
- `R2_sweep_reversal`: liquidity sweep, reclaim, 1m precision trigger.
- `R3_trendline_reversal`: 4h/1h/15m trendline touch/sweep/rejection with SR/FVG/liquidity overlap.
- `R4_break_retest_reversal`: clean break of a major trendline/SR, then underside/overside retest with 1m trigger.

Separate continuation variants:

- `C1_htf_aligned_fvg_pullback`
- `C2_breakout_retest_continuation`
- `C3_channel_or_trendline_continuation`

Reporting lock:

- R variants and C variants must have separate PnL, drawdown, PF, expectancy, target mix, and DNA audit.
- Continuation can be profitable, but it cannot be blended into headline reversal edge.
- `R3` and `R4` must report trendline quality and false-break rates.

## Target Pool Generator

Add:

- `target_pool_generator`

The target pool generator must run before trade acceptance. It builds structural targets visible at or before decision time.

### Allowed Target Sources

For long trades, search above entry:

- nearest 15m unmitigated bearish FVG midpoint.
- 15m resistance or SR zone.
- current day high so far.
- previous day high.
- next 15m FVG.
- next clear 1h/4h opposing PA zone.
- liquidity pool above.

For short trades, search below entry:

- nearest 15m unmitigated bullish FVG midpoint.
- 15m support or SR zone.
- current day low so far.
- previous day low.
- next 15m FVG.
- next clear 1h/4h opposing PA zone.
- liquidity pool below.

Fallback:

- fixed R targets may be used only after the structural target pool is built.
- Fixed R cannot be the primary optimization target for Craig DNA headline results.

### Target Object Schema

Each candidate target stores:

- `target_id`
- `target_side`: above or below
- `target_source`
- `timeframe`
- `zone_low`
- `zone_high`
- `target_price`
- `target_mid`
- `available_at`
- `freshness_state`
- `distance_r_gross`
- `distance_r_net`
- `target_quality_score`
- `opposing_reaction_risk`
- `used_as_tp1`
- `used_as_core`
- `used_as_runner`

Allowed `target_source` values:

- `nearest_15m_unmitigated_fvg_mid`
- `15m_sr_zone`
- `1h_sr_zone`
- `4h_sr_zone`
- `day_high_low`
- `previous_day_high_low`
- `next_15m_fvg`
- `next_1h_fvg`
- `liquidity_pool`
- `trendline_projection`
- `fixed_R`
- `none`

No-lookahead target rule:

- Current day high/low means high/low observed only up to the decision timestamp.
- A 15m FVG can be a target only after its confirming 15m candle has closed before decision time.
- A future FVG formed after entry cannot be used as pretrade TP. It may only affect live management after it becomes visible.

## TP / Runner Logic Refinement

Add fields:

- `tp1_target_source`
- `core_target_source`
- `runner_target_source`
- `opposing_trend_strength_score`
- `trade_confidence_score`
- `all_out_exit_allowed`
- `partial_then_runner_allowed`
- `runner_hold_permission`
- `target_conflict_reason`

Allowed `tp1_target_source`:

- `nearest_15m_unmitigated_fvg_mid`
- `15m_sr_zone`
- `day_high_low`
- `fixed_R`
- `none`

`core_target_source` and `runner_target_source` can use the full structural target-source list.

### TP Selection Principles

1. Build structural targets first.
   - Do not start by choosing 2R or 4R.
   - First identify meaningful 15m/1h/4h opposing zones.

2. Reject or declassify weak-R targets.
   - If the nearest meaningful target creates planned net RR < 3R, reject for DNA headline.
   - It may be logged as `lower_confidence_scalp_candidate`, but this bucket cannot contribute to Craig DNA headline metrics.

3. TP1 is not automatically 2R.
   - TP1 is the nearest meaningful 15m target if it is not too close.
   - If the nearest target is inside 1R, use it as conflict evidence, not a profit objective.
   - TP1 can be skipped if confidence and structure favor core target first.

4. Core target must preserve Craig high-R DNA.
   - Prefer 4R to 5R if that aligns with a 15m/1h opposing PA zone.
   - If the structural core target is beyond 5R, allow core at the first major opposing zone and runner beyond it.
   - If no structural core target exists and only fixed 4R exists, mark `target_conflict_reason=fixed_r_without_structure`.

5. Runner must be earned.
   - Runner requires a visible path toward 7R to 8R, current/previous day high/low, next 15m FVG, next SR zone, or 1h/4h liquidity.
   - Runner is not allowed when BTC strongly warns/vetoes, opposing HTF trend is strong, or a major opposing zone sits just beyond TP1.

6. All-out exit is allowed but controlled.
   - If confidence is lower, BTC warns, opposite trend is strong, or support/resistance starts holding at the first meaningful target, all-out at that target is allowed.
   - All-out at 1R repeatedly is a DNA failure.

### Confidence And Opposition Scores

Add:

- `trade_confidence_score`

Components:

- HTF thesis quality.
- SR/FVG/trendline/liquidity confluence.
- BTC context effect.
- 1m trigger quality.
- Entry proximity to invalidation.
- Planned net RR to structural target.
- Freshness of entry zone.
- Session phase and volatility.

Add:

- `opposing_trend_strength_score`

Components:

- 4h/1h trend against trade.
- 15m displacement against trade.
- BTC PA reaction against trade.
- Alt leader/laggard state.
- Opposing FVG/SR density before core target.
- Recent failed continuation in intended direction.

### Management Permissions

Set:

- `all_out_exit_allowed=true` when:
  - `trade_confidence_score` is low or medium,
  - first structural target is strong,
  - `opposing_trend_strength_score` is high,
  - `btc_context_effect` is `warn` or `veto`,
  - or price shows rejection at TP1 zone before core target permission is earned.

- `partial_then_runner_allowed=true` when:
  - TP1 is meaningful and >= 1.5R,
  - core target remains >= 3R net,
  - BE or profit-stop can be moved without choking structure,
  - and BTC is not vetoing.

- `runner_hold_permission=true` when:
  - core path remains open toward 4R to 5R,
  - runner target exists toward 7R to 8R or next major liquidity,
  - HTF thesis remains valid,
  - BTC context is confirm or neutral,
  - price has not rejected from a major opposing 15m/1h zone,
  - and stop can trail behind structure.

Set:

- `target_conflict_reason`

Allowed values:

- `nearest_target_too_close`
- `no_structural_target`
- `fixed_r_without_structure`
- `opposing_trend_too_strong`
- `btc_warn_or_veto`
- `major_sr_blocks_runner`
- `fvg_target_already_mitigated`
- `day_high_low_already_tagged`
- `none`

## Exit State Machine

Pre-entry:

1. Build HTF/15m thesis.
2. Build target pool.
3. Build entry/SL.
4. Compute planned net RR to TP1, core, runner.
5. Reject if no structural path to >= 3R.

After fill:

1. Stop remains at thesis invalidation unless BE/profit-stop condition triggers.
2. If TP1 target is reached:
   - all-out if permission says all-out.
   - partial if `partial_then_runner_allowed=true`.
   - hold through only if TP1 is weak and core permission is strong.
3. If core target is reached:
   - exit core size.
   - keep runner only if `runner_hold_permission=true`.
4. If BTC flips to warning/veto after entry using newly closed candles:
   - tighten runner permission.
   - permit all-out at next structural target.
5. If opposing SR/FVG/trendline rejects hard:
   - runner exits or trails aggressively.
6. If thesis invalidates:
   - exit. Do not widen stop.

## Craig DNA Audit Additions

Add hard DNA fail conditions:

- `fixed_R` is the dominant TP source in headline trades.
- Most wins exit at or below 1R without structural target rationale.
- Runner is disabled globally by optimization.
- Runner is always enabled without permission logic.
- BTC is modeled only as candle return or same-direction filter.
- Trendline PA zones are absent from the HTF thesis generator.
- Accepted trades lack SR/FVG/trendline/liquidity location.
- Target pool uses zones that formed after the decision timestamp.

Add audit metrics:

- `trendline_pa_zone_present_pct`
- `trendline_interaction_distribution`
- `trendline_pa_zone_score_median`
- `sr_zone_present_pct`
- `btc_htf_zone_present_pct`
- `btc_context_effect_confirm_pct`
- `btc_context_effect_warn_veto_pct`
- `btc_pa_reaction_state_distribution`
- `structural_target_pool_present_pct`
- `tp1_structural_source_pct`
- `core_structural_source_pct`
- `runner_structural_source_pct`
- `fixed_r_primary_target_pct`
- `nearest_target_too_close_reject_count`
- `lower_confidence_scalp_declassified_count`
- `planned_core_rr_net_median`
- `planned_runner_rr_net_median`
- `all_out_exit_rate`
- `all_out_exit_structural_reason_pct`
- `partial_then_runner_rate`
- `runner_hold_permission_rate`
- `runner_denied_by_btc_or_opposition_count`
- `target_conflict_reason_distribution`
- `tp1_only_profit_share`
- `runner_contribution_pct`
- `target_pool_lookahead_violation_count`

Suggested pass thresholds:

- `structural_target_pool_present_pct >= 90%`
- `core_structural_source_pct >= 70%`
- `fixed_r_primary_target_pct <= 20%`
- `planned_core_rr_net_median >= 3.5R`
- `accepted_trade_core_rr_ge_3r_pct >= 80%`
- `trendline_pa_zone_present_pct + sr_zone_present_pct + fvg_zone_present_pct >= 90%`
- `btc_htf_zone_present_pct >= 60%` for SOL/ETH headline trades.
- `tp1_only_profit_share <= 25%`
- `runner_hold_permission_rate >= 25%`
- `target_pool_lookahead_violation_count = 0`

## No-Lookahead Locks

The following are forbidden in signal, entry, target, and management permission generation:

- future candles,
- future swing anchors,
- future trendline anchors,
- future FVGs,
- realized outcome,
- gold fill state,
- gold result R/USD,
- Craig target action,
- hindsight TP that was identified only after price arrived.

Each accepted trade must write:

- `decision_timestamp`
- `latest_1m_close_used`
- `latest_15m_close_used`
- `latest_1h_close_used`
- `latest_4h_close_used`
- `target_pool_built_at`
- `trendline_anchors_latest_time`
- `btc_context_built_at`
- `lookahead_pass`

Any `lookahead_pass=false` invalidates the run.

## v1.2 Build Order

1. Create config.
   - `outputs/craig_v1_2_backtest_config.yaml`
   - Include mode, symbols, fees, slippage, target-source priority, walk-forward windows, DNA thresholds.

2. Build no-lookahead market feature store.
   - Script: `scripts/build_craig_v1_2_market_features.py`
   - Output: `outputs/craig_v1_2_market_feature_snapshots.parquet`
   - Include 1m/5m/15m/1h/4h closed-candle alignment.

3. Build HTF zone and trendline detector.
   - Script: `scripts/build_craig_v1_2_htf_zones.py`
   - Outputs:
     - `outputs/craig_v1_2_htf_zones.parquet`
     - `outputs/craig_v1_2_trendline_zones.parquet`
   - Include FVG, SR, liquidity, day high/low so far, trendline touch/sweep/break-retest.

4. Build BTC context engine.
   - Script: `scripts/build_craig_v1_2_btc_context.py`
   - Output: `outputs/craig_v1_2_btc_context_snapshots.parquet`
   - Include BTC PA zone, trendline interaction, reaction state, context effect.

5. Build thesis generator.
   - Script: `scripts/build_craig_v1_2_thesis_snapshots.py`
   - Output: `outputs/craig_v1_2_thesis_snapshots.parquet`
   - Include mode classification and hard rejects.

6. Build structural target pool.
   - Script: `scripts/build_craig_v1_2_target_pools.py`
   - Output: `outputs/craig_v1_2_target_pools.parquet`
   - Include TP1/core/runner candidate selection and target conflict reasons.

7. Build DNA-locked trade constructor.
   - Script: `scripts/build_craig_v1_2_trade_candidates.py`
   - Output: `outputs/craig_v1_2_trade_candidates.parquet`
   - Include entry, SL, TP1, core, runner, permission fields, planned net RR.

8. Run event-driven backtest.
   - Script: `scripts/run_craig_v1_2_dna_locked_backtest.py`
   - Outputs:
     - `outputs/craig_v1_2_dna_locked_trade_log.csv`
     - `outputs/craig_v1_2_dna_locked_equity_curve.csv`
     - `outputs/craig_v1_2_dna_locked_execution_audit.csv`

9. Run walk-forward validation.
   - Script: `scripts/run_craig_v1_2_walk_forward.py`
   - Outputs:
     - `outputs/craig_v1_2_dna_locked_fold_metrics.csv`
     - `outputs/craig_v1_2_dna_locked_parameter_selection.csv`

10. Run Craig DNA and leakage audit.
    - Script: `scripts/audit_craig_v1_2_dna_character.py`
    - Outputs:
      - `outputs/craig_v1_2_dna_character_audit.csv`
      - `outputs/craig_v1_2_leakage_audit.csv`

11. Write final validation report.
    - Script: `scripts/write_craig_v1_2_validation_report.py`
    - Output: `outputs/craig_v1_2_dna_locked_validation_report.md`

## Acceptance Rule

v1.2 is accepted only if both are true:

1. Independent walk-forward net performance is promising: positive expectancy, acceptable drawdown, profit factor above 1 after realistic costs, and no single-outlier dependency.
2. Craig DNA audit passes: high-R structural targets, HTF/15m thesis, BTC PA context, trendline/SR/FVG/liquidity location, thesis-invalidation stop, no-chase, and runner/all-out permission logic remain intact.

A profitable run that becomes 1R scalping, 1m-only signaling, fixed-R-only exits, or wide-stop win-rate holding is a failed v1.2 strategy.
