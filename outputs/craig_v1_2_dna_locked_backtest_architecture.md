# Craig v1.2 DNA-Locked Backtest Architecture

Generated for the pivot from Craig-imitation replay to Craig-derived independent systematic strategy validation.

## Objective

v1.1 is frozen as the Craig-imitation checkpoint. v1.2 evaluates whether Craig-derived principles can become an independent, repeatable, automated strategy with positive net expectancy and acceptable drawdown.

Craig labels, realized outcomes, future candles, and gold target actions are not optimization targets. They may be used only for provenance, diagnostics, and Craig-character audit.

The strategy must preserve Craig DNA:

- Seek asymmetric high-R trades, not low-R repetition.
- Require planned RR >= 3R before entry.
- Use 4R to 5R as the core target zone and preserve 7R to 8R runner optionality.
- Do not optimize into 1R scalping.
- Require 15m/1h/4h top-down thesis, PA zone, liquidity, FVG/SR context.
- Use 1m precision entries near thesis-defined invalidation.
- Prioritize reversal-at-extreme, sweep reversal, and small-risk large-upside structures.
- Keep continuation as a separate variant.
- Include no-chase, cancel, invalidation, and fast thesis revision rules.

## System Layers

1. Market data layer
   - Source: exchange OHLCV, preferably 1m base candles.
   - Resample from 1m into 5m, 15m, 1h, and 4h using closed candles only.
   - Maintain timestamp alignment audit for every feature.

2. HTF thesis generator
   - Produces directional bias, thesis confidence, active PA zones, HTF invalidation, and target pools.
   - Uses only 15m, 1h, and 4h candles completed before the decision timestamp.

3. Mode classifier
   - Classifies each candidate into `reversal_extreme`, `sweep_reversal`, `continuation_pullback`, or `reject`.
   - Reversal modes are primary. Continuation is a separate variant and must be reported separately.

4. 1m precision entry engine
   - Waits for a low-timeframe trigger inside the HTF thesis zone.
   - Builds deterministic entry, SL, TP, runner, expiry, and cancel rules.

5. Execution simulator
   - Event-driven candle replay from decision time forward.
   - Simulates order fill, no-fill, cancel, stop, partial, runner, session close, fee, and slippage.

6. Portfolio/risk engine
   - Converts each trade into R-multiple and account-level equity.
   - Enforces max risk per trade, max daily loss, cooldown, and max concurrent exposure.

7. Reporting/audit layer
   - Outputs trade log, fold metrics, segment metrics, Craig-character audit, leakage audit, and robustness report.

## HTF / 15m Thesis Generator

Required inputs:

- 4h trend or displacement context.
- 1h range location and premium/discount proxy.
- 15m PA zone, FVG/SR cluster, liquidity sweep candidate, displacement leg, and active invalidation.
- BTC/ETH leader alignment for alt trades.
- Session phase and volatility regime.

Candidate thesis fields:

- `thesis_side`: long, short, or none.
- `thesis_mode`: reversal_extreme, sweep_reversal, continuation_pullback.
- `htf_zone_kind`: FVG, SR flip, range extreme, liquidity pool, order-block proxy.
- `zone_low`, `zone_high`, `zone_mid`.
- `invalidation_price`.
- `core_target_price`.
- `runner_target_price`.
- `planned_rr_core`.
- `planned_rr_runner`.
- `thesis_score`.
- `reject_reasons`.

Hard rejects:

- No completed 15m/1h/4h context.
- No identifiable HTF zone.
- No thesis invalidation price.
- Planned core RR < 3R.
- Entry would be in the middle of range with no extreme, sweep, or clear continuation context.
- Leader context strongly contradicts the thesis and no sweep/reversal evidence exists.

## Reversal vs Continuation Separation

Primary strategy variants:

- `R1_reversal_extreme`: price reaches HTF range extreme, PA zone, or liquidity pool, then shows LTF rejection.
- `R2_sweep_reversal`: price sweeps prior high/low or liquidity pool, reclaims, then offers 1m retrace entry.

Secondary variant:

- `C1_continuation_pullback`: HTF trend aligned, displacement already confirmed, entry on pullback into FVG/SR.

Reporting rules:

- Do not combine reversal and continuation metrics into one headline edge.
- Report each variant separately by expectancy, PF, drawdown, frequency, and runner contribution.
- A profitable continuation result cannot rescue a failing reversal result.
- A profitable 1m-only continuation result is rejected if HTF thesis requirements are not met.

## High-R Trade Construction

Entry models:

- `limit_fvg_mid`: entry at 1m or 5m FVG midpoint inside HTF zone.
- `limit_retest_edge`: entry at reclaimed SR/FVG edge after sweep and displacement.
- `confirmation_market`: next 1m open after reclaim/displacement confirmation. This is a separate variant because it usually worsens RR.

Entry constraints:

- Entry must be inside or adjacent to a thesis-approved 15m/1h zone.
- Entry must be within a maximum ATR distance from invalidation.
- Entry must preserve planned core RR >= 3R after fees/slippage estimate.
- Prefer entries with core RR 4R to 5R and runner RR 7R to 8R.
- Reject trades where high RR exists only because the stop is artificially tiny and unrelated to invalidation.

No-chase rules:

- If price moves 1.5R to 2R in the intended direction before fill, cancel the order.
- If entry is missed and price reaches the first displacement objective, no market chase.
- If RR compresses below 3R before fill, cancel.
- If thesis zone is fully mitigated and no fresh lower-timeframe trigger appears, cancel.

## Stop Logic

Stop must be thesis invalidation based:

- Long: below sweep low, FVG/zone low, or local structure low plus ATR/tick buffer.
- Short: above sweep high, FVG/zone high, or local structure high plus ATR/tick buffer.

Invalid stop designs:

- Stop widened after entry to avoid loss.
- Stop placed far outside thesis invalidation just to improve win rate.
- Stop derived from future swing points.
- Stop so tight it is inside normal spread/noise and unrelated to structure.

Stop audits:

- `stop_to_atr`.
- `stop_to_zone_width`.
- `stop_distance_pct`.
- `invalidation_anchor_type`.
- `planned_rr_core_after_cost`.

## TP / Runner Logic

Baseline management:

- TP1: optional partial at 2R only for risk reduction, not as the main strategy objective.
- Core target: 4R to 5R or nearest opposing HTF liquidity/PA zone if >= 3R.
- Runner: 7R to 8R target or HTF opposing zone.
- BE move: after structural acceptance, TP1, or clean displacement away from entry.
- Runner stop: trail behind 1m/5m structure only after core target or confirmed continuation.

Allowed result attribution:

- `core_R`: realized from core target or core exit.
- `runner_R`: additional realized R after core logic.
- `runner_contribution_pct`: runner_R / total_positive_R.
- `tp1_only_exit_rate`: must stay low; high value signals DNA drift.

DNA guardrails:

- The strategy cannot be optimized to exit all trades at 1R.
- A parameter set is rejected if most positive expectancy comes from 1R/TP1 exits while core/runner contribution is weak.
- Runner optionality must be measurable even if many trades stop at BE after partial.

## Execution, Fees, and Slippage

Fill assumptions:

- Limit entry fills when candle range touches entry.
- Market confirmation fills at next candle open with taker cost.
- Same-candle entry/stop/target ambiguity uses conservative ordering by default.
- Ambiguous rows are counted separately and stress-tested.

Fee model:

- Configurable maker fee bps.
- Configurable taker fee bps.
- Round-trip fee is deducted from R based on stop distance.

Slippage model:

- Entry limit: 0 to low bps baseline.
- Market entry: taker slippage.
- Stop: adverse slippage.
- Stress grid: base, 2x, 5x costs.

Cost-adjusted RR:

- Every trade stores gross planned RR and net planned RR.
- Reject if net planned core RR < 3R.

## No-Lookahead Validation

Feature rules:

- Every HTF feature must use candles whose close time is <= decision timestamp.
- FVG/SR/CHoCH/BOS objects become available only after the confirming candle closes.
- No realized outcome, gold fill state, gold result, future high/low, or future swing can enter signal generation.
- Candidate side must be generated from market state, not copied from Craig labels.

Audit outputs:

- `feature_timestamp`.
- `source_candle_close_time`.
- `decision_timestamp`.
- `lookahead_violation`.
- `gold_label_columns_used`.
- `future_window_accessed_before_trade`.

Any lookahead violation invalidates the run.

## Walk-Forward Test Design

Minimum process:

- Train window: 90 to 180 calendar days.
- Validation window: 30 to 60 days.
- Test window: 30 to 60 days.
- Embargo: at least 1 trading day between windows, plus open-trade liquidation at split boundary.

Parameter selection:

- Optimize only on train/validation.
- Select robust plateaus, not single best points.
- Freeze parameters before test fold.
- Aggregate test folds as the headline result.

Parameter families:

- Thesis score threshold.
- Zone freshness threshold.
- Entry model.
- Order expiry.
- No-chase R threshold.
- Stop buffer ATR multiplier.
- Core target R.
- Runner target R.
- BE trigger.
- Session filter.
- Leader alignment filter.

Robustness requirements:

- Positive expectancy across most test folds.
- Profit factor > 1 after realistic costs.
- Drawdown not dominated by one period or one symbol.
- Top 5 trades cannot explain all profitability.
- Runner contribution present but not solely one outlier.

## Performance Metrics

Primary:

- Net total R.
- Net expectancy per trade.
- Profit factor.
- Max drawdown in R.
- Return/drawdown.
- Trade count and trades per week.
- Win/loss/BE rate.
- Average win, average loss, payoff ratio.

High-R distribution:

- Median R.
- 75th/90th/95th percentile R.
- Count of trades >= 3R, >= 5R, >= 8R.
- Share of wins from core target.
- Share of wins from runner.
- Largest winner dependency.

Execution:

- Fill rate.
- No-fill rate.
- Missed-no-chase rate.
- Cancel rate.
- Same-candle ambiguity rate.
- Average slippage cost in R.
- Fee drag in R.

Risk:

- Max losing streak.
- Worst day and worst week.
- Daily loss cap hit count.
- Time in market.
- Concurrent exposure.

Segments:

- Mode: reversal_extreme, sweep_reversal, continuation_pullback.
- Symbol.
- Side.
- Session.
- Volatility regime.
- HTF bias alignment.
- Range location.
- FVG freshness.
- Setup score bucket.
- Entry model.

## Craig-Character Audit

The strategy can pass PnL but fail Craig DNA. Both must be reported.

Hard DNA fail conditions:

- Median planned core RR < 3R.
- More than 25% of accepted trades have planned core RR < 3R.
- Primary realized profit comes from 1R-only exits.
- HTF thesis missing on accepted trades.
- Most trades are generated from 1m-only signals.
- Stops are systematically widened beyond thesis invalidation.
- Continuation trades are mixed into reversal headline metrics.
- No-chase rule is disabled or rarely enforced despite missed entries.

Craig DNA metrics:

- `planned_rr_core_median`.
- `planned_rr_runner_median`.
- `accepted_trade_core_rr_ge_3r_pct`.
- `core_target_4_5r_share`.
- `runner_7_8r_available_share`.
- `runner_contribution_pct`.
- `tp1_only_profit_share`.
- `htf_thesis_present_pct`.
- `fifteen_min_zone_present_pct`.
- `one_min_precision_entry_pct`.
- `thesis_invalidation_stop_pct`.
- `reversal_mode_share`.
- `continuation_mode_share`.
- `no_chase_cancel_count`.
- `rr_compression_cancel_count`.
- `invalidation_cancel_count`.
- `dna_pass`.

Suggested DNA pass thresholds for v1.2:

- Median planned core RR >= 3.5R.
- At least 80% accepted trades have planned core RR >= 3R.
- At least 70% accepted trades have explicit 15m/1h/4h thesis.
- At least 70% accepted trades use thesis invalidation stop.
- At least 60% of primary headline trades are reversal or sweep-reversal.
- TP1-only profit share <= 25%.
- Runner path available in at least 40% of accepted trades.

## v1.2 Deliverables

- `scripts/run_craig_v1_2_dna_locked_backtest.py`
- `outputs/craig_v1_2_dna_locked_trade_log.csv`
- `outputs/craig_v1_2_dna_locked_fold_metrics.csv`
- `outputs/craig_v1_2_dna_locked_segment_metrics.csv`
- `outputs/craig_v1_2_dna_character_audit.csv`
- `outputs/craig_v1_2_dna_locked_validation_report.md`
- `outputs/craig_v1_2_backtest_config.yaml`

## Recommended Build Order

1. Freeze and reference v1.1 artifacts without mutating them.
2. Build no-lookahead OHLCV feature engine.
3. Build HTF thesis generator and Craig DNA audit fields.
4. Build reversal variants R1/R2 first.
5. Add 1m precision entry and thesis-invalidation stop constructor.
6. Add core/runner management and cost model.
7. Add walk-forward harness.
8. Add continuation variant C1 separately.
9. Produce PnL report and Craig-character audit side by side.

v1.2 should be judged only when both conditions hold: independent net performance is promising, and Craig DNA audit passes.
