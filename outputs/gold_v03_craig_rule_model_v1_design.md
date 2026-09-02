# Craig Gold v0.3 Rule Model v1 Design

Generated: 2026-08-24

## Technical Summary

The v1 Craig copy model should be a rule-based decision replay engine, not a generic profitable FVG scanner. The target is: given only chart data plus same-day news/macro conditions, reproduce Craig's decision state under the same conditions: take, wait, pass, cancel, no-fill, hold, manage, or reassess.

The current gold context is strong enough to design the ontology and start v1 feature extraction. The two core files join cleanly: `gold_v03_trade_context_queue.csv` has 149 decision rows, `gold_v03_rule_seed_queue.csv` has 149 matching rule-seed rows, and there are no duplicate `context_id` values. The context spans 32 sessions, with 5 additional hold rows kept outside gold.

The main blocker for numerical backtesting is not missing prose context. It is missing machine-readable setup geometry. `entry_price`, `stop_price`, and `target_price` are populated as fields, but only 9/149 entry values, 7/149 stop values, and 7/149 target values are plain numeric. v1 should therefore start with relative-structure replay and only use exact candle fill/SL/TP simulation where geometry can be extracted or inferred with explicit confidence.

The model should keep incomplete context as first-class `hold/unknown`, exactly matching the existing gold standard. Do not infer Elliott wave, trendlines, true entry zones, news bias, or management triggers when the source row does not support them.

## Evidence Profile

| Check | Result | Modeling implication |
|---|---:|---|
| Trade context rows | 149 | Enough for ontology and rule families, not enough for unrestricted optimization. |
| Rule seed rows | 149 | Complete 1:1 seed coverage against trade contexts. |
| Session maps | 32 | Session-level state should be modeled separately from decision rows. |
| Hold contexts | 5 | Use as exclusion/hold tests, not as positive trade labels. |
| `context_id` join gaps | 0 | Safe to build normalized units by joining the two core CSVs. |
| Raw `decision_type` distinct values | 90 | Must normalize before modeling. |
| Raw `direction` distinct values | 26 | Must normalize into `long`, `short`, `conditional`, `mixed`, `unknown`. |
| Gold statuses | 68 trade, 43 actionable, 38 context | Treat executed, actionable/no-fill, and pass/cancel as separate labels. |
| OHLCV market dates | 36 | Most later dates have BTC/ETH/SOL 1m cache; several early 2024 dates are missing. |
| Local frames in quality audit | 29 yes, 3 legacy-only | Legacy-only rows need lower geometry confidence. |

Decision bucket heuristic from current rows:

| Bucket | Rows | Use |
|---|---:|---|
| `executed_trade_or_trade_context` | 90 | Entry/management/outcome rule calibration. |
| `actionable_no_fill_or_pre_fill` | 54 | Entry discipline, no-fill, no-chase, cancel rules. |
| `explicit_pass_or_cancel` | 5 | High-value negative/pass rules; expand with normalized labels. |

## Ontology

Model the dataset as decision units inside session state:

1. `SessionState`: market date, session phase, macro/news regime, HTF bias, key levels, volatility, current day PnL/risk pressure.
2. `SymbolState`: candidate symbols, relative strength/weakness, cleaner setup ranking, selected symbol, switch reason.
3. `ThesisState`: bullish, bearish, conditional, open-ended, or invalidated thesis; includes HFT/daily/wave/fib context when stated.
4. `SetupCandidate`: structure that makes a trade possible: FVG, CHoCH/BOS, SR flip, trendline retest, sweep, order block, Fib/wave overlap, pattern, liquidity draw.
5. `EntryPlan`: entry zone, order type, stop model, target model, no-chase rule, fill expectation.
6. `ExecutionState`: no trigger, no-fill, missed by fraction, filled, partial, reentry, execution anomaly.
7. `ManagementState`: BE, partial, profit stop, trail, runner hold, manual flat, daily-goal exit, risk reduction after adverse evidence.
8. `OutcomeState`: TP, stop, BE, manual close, flat, small win, missed move, canceled, hold/unknown.
9. `EvidenceState`: source confidence, frame availability, OHLCV alignment, numeric geometry availability, unresolved uncertainty.

The core state transition:

`observe -> form_thesis -> rank_symbol -> wait_for_setup -> plan_entry -> wait_for_touch -> execute_or_no_fill -> manage -> exit`

Alternative exits:

`pass`, `cancel`, `hold_unknown`, `discard_not_gold`, `reassess_thesis`, `switch_symbol`.

## Taxonomy

### Macro, HFT, And Session Bias

Categories:

| Category | Examples from gold context | Feature direction |
|---|---|---|
| Same-day macro/news | FOMC/tariff day, Nvidia earnings, no high-impact news, news pump/dump volatility | Requires external calendar/news snapshot plus row evidence. |
| Session phase | NY open, late morning, afternoon, power hour, dinner/gym/overnight/Asia | Deterministic from verified market time. |
| Daily/HTF directional bias | bearish daily pressure, bullish close above key level, no-bias/open-ended | OHLCV-derived score plus text-derived label. |
| HTF key levels | PDH/PDL, 15m/1h/4h FVG, critical SR, range high/low, liquidity draw | OHLCV detector plus manual/frame confidence. |
| Volatility/HFT regime | news expansion, chop, calm trend, displacement candle, high-volatility BE requirement | ATR/body/range/volume features. |
| Wave/Fib context | wave 5 extension, 2.618/3.618/4.618, ABC/G2 continuation | Only when stated or anchored; otherwise `unknown`. |
| Session risk context | daily goal, after big win, risk per trade, capital preservation, gym/dinner constraints | Text-to-enum plus state variables. |

### Symbol Selection

Craig does not simply trade the symbol with the latest FVG. He chooses the symbol whose structure is cleaner under the current thesis.

Categories:

| Category | Feature |
|---|---|
| Candidate universe | `candidate_symbols = {BTCUSDT, ETHUSDT, SOLUSDT, ATOM}` with `primary_symbol`. |
| Cleaner setup | rank by HTF confluence, FVG freshness, CHoCH quality, RR, stop clarity, trendline/SR alignment. |
| Relative bias | BTC leader, ETH/SOL lag/strength, pair divergence. |
| Switch reason | failed SOL setup, cleaner ETH CHoCH/FVG, no-fill on first symbol, later session strength. |
| Conditional multi-symbol | rows like `SOLUSDT/ETHUSDT` or `BTCUSDT|SOLUSDT` become comparison states, not single-symbol labels. |

### Setup Trigger

Primary trigger families:

| Trigger | Quantification status |
|---|---|
| FVG midpoint/retest | Ready with OHLCV detector, but geometry confidence varies. |
| CHoCH/BOS/displacement | Ready as heuristic; needs strict/micro enum. |
| SR flip / overside / underside retest | Partial; pivot clusters can approximate but manual levels need confidence. |
| Trendline retest | Partial; swing-line detector is lower confidence than frame evidence. |
| Sweep/liquidity grab | Partial; OHLCV can detect sweep, but Craig's intended liquidity draw may be manual. |
| Order block / response area | Partial/hold; needs frame or robust heuristic. |
| Elliott/Fib overlap | Hold unless source states wave anchors or detector can derive them with confidence. |
| Head-and-shoulders / pattern context | Text/frame-derived initially; automate later only if recurring enough. |

### Entry

Entry categories:

| Entry class | Model behavior |
|---|---|
| FVG midpoint limit | Wait for midpoint/zone touch; no market chase if price runs. |
| Deep buy/sell ladder | Represent as multiple planned zones with shared thesis and stop family. |
| Overside/underside retest | Requires level reclaim/break plus retest. |
| Response-area retest | Enter only after displacement/CHoCH, then pullback holds. |
| Fast market entry | Rare and only after strong displacement; should not be default. |
| Planned no-fill | Valid Craig decision; label `no_fill`, not missed model error. |
| Cancel/no-chase | If true FVG/level touch already occurred or RR compressed, cancel/pass. |

### Invalidation

Invalidation families:

| Family | Quantifiable condition |
|---|---|
| FVG invalidation | Close beyond FVG boundary against direction. |
| Key level reclaim | Price reclaims support/resistance against thesis. |
| Stop structure | Stop beyond swing, defended low/high, zone boundary, or volatility stop. |
| No follow-through | Expected high/low/neckline close fails after entry. |
| Late recognition | Original touch already happened; new entry becomes chase. |
| News/macro blackout | High-impact event too close unless setup is complete before event. |
| RR compression | Entry too far from stop or too close to target after move. |

### Management

Management is a state machine, not a static TP/SL rule:

| Management class | Rule implication |
|---|---|
| BE after confirmation | Move stop to BE after favorable close above/below trigger, low/high break, or enough MFE. |
| Partial/profit stop | Lock profit when volatility is high, macro is against, or follow-through weakens. |
| Runner hold | Hold if BE is secured and HTF liquidity/daily goal still supports move. |
| Structure trail | Trail behind lower highs/higher lows, trendline, equal lows/highs, or key retests. |
| Manual flat | Exit flat/small win when price action contradicts thesis before hard stop. |
| Daily goal preservation | After goal or big win, reduce willingness to force marginal trades. |
| Execution anomaly | Exclude fat-finger/oversize PnL from strategy edge. |

### Live Thesis Change

Categories:

| Thesis change | v1 state transition |
|---|---|
| Missed good entry | `plan -> pass/cancel`, keep thesis but no chase. |
| Failed expected dump | bearish thesis becomes `open_ended` or long-strength candidate. |
| Daily bias challenged | bias stays as context but 1m confirmation can permit counter-trade. |
| Failed trade but same thesis remains | allow reentry only with fresh confirmation and cooldown. |
| Symbol switch | re-rank symbols after failed/no-fill/dirty structure. |
| News regime shift | volatility rules override normal patience/BE/target behavior. |

### Pass, No-Fill, Hold

Positive negative labels:

| Label | Meaning |
|---|---|
| `pass_no_chase` | Good setup already touched or price ran too far. |
| `planned_no_fill` | Setup was valid, but entry zone never filled. |
| `cancel_before_fill` | Craig cancels because original premise was late/invalidated. |
| `wait_for_new_structure` | Needs a fresh break, CHoCH, or level retest. |
| `hold_unknown` | Evidence is insufficient; not a trade label. |

Hold reasons from current data:

| Hold reason | Current examples |
|---|---|
| Setup geometry missing | `that level` / recap-only / no clear entry-SL-TP. |
| Symbol or direction unknown | short/long spoken ambiguously or not visible. |
| Frame recovery needed | MP4 corruption after a timestamp; SRT-only trade cluster. |
| Result/journal mismatch | trade exists but final PnL/result not matched. |
| Management-only context | useful behavior, not complete entry rule evidence. |

## Feature Convertibility Classes

| Class | Meaning | Examples |
|---|---|---|
| `direct_field` | Can be normalized from current CSV fields. | `context_id`, `video_id`, source stage, raw status, hold status. |
| `text_to_enum` | Can be extracted from prose with human-reviewed mapping. | decision label, pass reason, entry model, management family. |
| `ohlcv_derived` | Deterministic detector from candles once timestamp/geometry exists. | session phase, ATR, FVG, PDH/PDL, displacement. |
| `ohlcv_heuristic` | Detector possible but not a perfect proxy for Craig drawings. | CHoCH strictness, SR flip, trendline, sweep, order block. |
| `external_required` | Needs same-day news/calendar input. | high-impact news window, FOMC/CPI/tariff/earnings regime. |
| `cv_or_numeric_required` | Needs frame/OCR/manual geometry to backtest fills exactly. | entry/stop/target price, position box, missed-by-fraction. |
| `hold_unknown` | Do not infer until evidence is added. | unstated Elliott wave count, ambiguous symbol/direction, corrupt-frame cluster. |

The full feature audit matrix is saved as `outputs/gold_v03_feature_audit_v1.csv`.

## Missing Evidence Audit

Highest-priority gaps:

| Gap | Current evidence | Required v1 field |
|---|---|---|
| Canonical decision labels | 90 raw `decision_type` values | `decision_label`, `decision_subtype`, `fill_state`, `management_state`. |
| Direction enum | 26 raw direction values | `primary_direction`, `direction_state`, `conditional_directions`. |
| Symbol enum | combined symbols in one field | `primary_symbol`, `comparison_symbols`, `symbol_switch_from/to`. |
| Numeric geometry | entry numeric 9/149, stop 7/149, target 7/149 | `entry_zone_low/high/mid`, `stop_level`, `target_levels[]`, `geometry_confidence`. |
| Decision timestamp | many rows have windows or prose time notes | `decision_time_start/end_utc`, `decision_time_confidence`, `replay_time`. |
| OHLCV alignment | currently prose in `ohlcv_alignment_ko` | machine enum: `available`, `aligned`, `contradiction`, `not_available`. |
| News/macro snapshot | news appears in prose only | `calendar_events[]`, `news_regime`, `minutes_to_event`, `news_source`. |
| Management triggers | often prose-only | `be_trigger_type/time`, `partial_trigger_type/time`, `trail_rule`, `manual_exit_reason`. |
| Outcome numeric | result prose and dollars/R mixed | `result_r`, `result_usd`, `exit_reason`, `outcome_confidence`. |
| Hold reason | hold rows are clear but not enum-normalized | `hold_reason_code`, `missing_required_fields[]`. |

Keep these as audit fields rather than hidden assumptions. A row can still train qualitative action selection while being excluded from exact fill simulation.

## V1 Rule Engine Design

### Inputs

Required inputs:

| Input | Source |
|---|---|
| Gold context rows | `gold_v03_trade_context_queue.csv` |
| Rule seed rows | `gold_v03_rule_seed_queue.csv` |
| Session maps | `gold_v03_video_session_maps.csv` |
| Hold rows | `gold_v03_hold_context_queue.csv` |
| OHLCV | BTCUSDT/ETHUSDT/SOLUSDT 1m cache, resampled to 5m/15m/1h/4h/1d |
| Macro/news | Same-day calendar and news snapshot supplied to model; do not fetch implicitly in replay |

### Normalized Data Layer

Create:

`data/processed/gold_context_trades/gold_v03_normalized_decision_units.csv`

Minimum fields:

| Field group | Fields |
|---|---|
| Identity | `decision_unit_id`, `context_id`, `session_context_id`, `video_id`, `source_stage_v03`. |
| Label | `decision_label`, `decision_subtype`, `gold_training_role`, `hold_reason_code`. |
| Time | `market_date`, `decision_time_start_utc`, `decision_time_end_utc`, `time_confidence`. |
| Symbol/direction | `primary_symbol`, `comparison_symbols`, `primary_direction`, `direction_state`. |
| Setup | `setup_family[]`, `entry_model`, `invalidation_family[]`, `management_family[]`. |
| Geometry | `entry_zone_low/high/mid`, `stop_level`, `target_1/2`, `geometry_confidence`. |
| Outcome | `fill_state`, `exit_reason`, `result_r`, `result_usd`, `outcome_confidence`. |
| Evidence | `frame_confidence`, `ohlcv_alignment_status`, `remaining_uncertainty_code`. |

Create:

`data/processed/features/gold_v03_feature_snapshots.parquet`

One row per decision time per candidate symbol:

| Feature group | Examples |
|---|---|
| Session | phase, minutes from NY open, macro/news state, volatility regime. |
| HTF | daily/4h/1h/15m trend score, range location, PDH/PDL proximity. |
| Zones | active FVGs, SR clusters, trendline zones, liquidity draws. |
| LTF trigger | 1m FVG, CHoCH type, displacement score, sweep/fail signal. |
| Symbol rank | relative return, leader alignment, setup cleanliness score. |
| Risk | RR if geometry known, risk width, target distance, late/chase distance. |
| State | prior trade result, trade count day, current PnL, cooldown, bias state. |

### Rule Engine Phases

1. Evidence gate:
   - If required label/time/symbol/direction/setup evidence is missing, output `hold_unknown`.
   - If row is execution anomaly, exclude from core strategy outcome but keep as negative behavior rule.

2. Session and macro gate:
   - Identify session phase, high-impact news window, volatility regime, and HTF bias.
   - News does not automatically block trades. It changes allowed entry/BE/target behavior.

3. Symbol selection:
   - Build candidate features for BTC/ETH/SOL.
   - Select highest `clean_setup_score` if it matches Craig's stated candidate set.
   - If no symbol has clean structure, output `wait`.

4. Setup trigger:
   - Require HTF reason plus LTF trigger.
   - LTF trigger is usually FVG + CHoCH/displacement/SR/trendline response.
   - Wave/Fib adds confluence only when explicitly supported.

5. Entry discipline:
   - Prefer planned zone/limit/retest.
   - If price misses planned zone and target/RR compresses, output `no_fill` or `pass_no_chase`.
   - If true touch already happened, cancel.

6. Invalidation:
   - FVG/key level reclaim or failed confirmation invalidates.
   - If against-thesis response appears before stop and Craig-style manual flat condition is met, output `manage_flat`.

7. Management:
   - Move to BE only after the row's management family condition is met.
   - Permit partial/profit stop in high volatility or counter-bias trades.
   - Permit runner only when BE/profit is secured and HTF target remains valid.

8. Output:
   - `take`, `wait`, `pass`, `cancel`, `no_fill`, `hold_unknown`, `manage`, `exit`.
   - Include `rule_trace[]` with every fired gate and every unknown.

### Example Rule Skeleton

```text
IF evidence.required_missing THEN hold_unknown
IF execution_anomaly THEN exclude_from_core_outcome

IF high_impact_news_window AND setup_not_complete_before_event THEN wait
IF no_htf_reason AND weak_ltf_displacement THEN wait

FOR each candidate_symbol:
  score clean setup from HTF zones + FVG freshness + CHoCH + RR + relative strength

IF best_symbol_score < threshold THEN wait
IF true_entry_touch_already_passed AND rr_compressed THEN pass_no_chase
IF planned_entry_zone_not_touched AND price_runs_to_target_side THEN no_fill

IF filled:
  IF favorable_close_breaks_trigger THEN move_stop_be
  IF followthrough_fails AND manual_flat_condition THEN exit_flat_or_small
  IF htf_draw_valid AND profit_locked THEN runner_hold
  ELSE exit_at_target_or_stop
```

## Backtest Design

Use two different evaluations.

### 1. Decision Replay Backtest

Purpose: reproduce Craig decisions at known gold decision windows.

Unit: one `DecisionUnit`.

Inputs available to the engine:

- Candles only up to decision time.
- Same-day macro/news snapshot only up to decision time.
- Prior session state only from earlier decisions.
- No outcome leakage.

Metrics:

| Metric | Definition |
|---|---|
| Action accuracy | `take/wait/pass/cancel/no_fill/hold/manage` match. |
| Direction accuracy | long/short/conditional match when action is trade-relevant. |
| Symbol accuracy | primary selected symbol match. |
| Setup family match | FVG/CHoCH/SR/trendline/wave/news-open etc. |
| Pass/no-fill recall | critical for Craig-style discipline. |
| Management trigger match | BE/partial/trail/manual flat/runner decision. |
| Unknown discipline | model returns `hold_unknown` when evidence is missing. |

This is the primary v1 test.

### 2. Market Scan Backtest

Purpose: scan full market days for Craig-like opportunities and stress test rules.

Use only after decision replay is stable. This mode can produce opportunities Craig did not discuss, so it should not be used as proof of Craig reproduction. It is useful for loss-pattern diagnostics and filter sensitivity.

Metrics:

- trade count/day,
- total R and drawdown,
- loss clusters by session/HTF bias/displacement,
- profitable missed traces,
- false positives around news, chop, and no-bias conditions.

## Implementation Plan

Recommended files:

| File | Purpose |
|---|---|
| `scripts/build_gold_v03_normalized_units.py` | Normalize decision labels, symbols, directions, hold reasons. |
| `scripts/build_gold_v03_feature_snapshots.py` | Build candle/news/state features per decision and candidate symbol. |
| `configs/craig_rule_model_v1.yaml` | Thresholds, rule ordering, enum maps, feature toggles. |
| `scripts/run_craig_decision_replay_v1.py` | Primary reproduction test against gold rows. |
| `scripts/run_craig_market_scan_backtest_v1.py` | Secondary full-day scan. |
| `outputs/gold_v03_decision_replay_v1_report.md` | Accuracy, mismatch audit, hold/unknown audit. |

Do not overwrite the v0.3 gold CSVs. Treat them as immutable source evidence and create derived normalized files.

## Validation And Robustness

Minimum v1 gates:

1. No training/evaluation row may use future candles beyond decision time.
2. Outcome fields cannot participate in entry/action scoring.
3. Rows with missing symbol/direction/setup geometry must emit `hold_unknown` for geometry-dependent rules.
4. Execution anomalies must not improve or hurt core strategy edge.
5. Split evaluation by video/session, not random row, to avoid same-session leakage.
6. Separate qualitative decision replay from exact fill simulation.
7. Every rule output must include a trace showing fired rules and unknown fields.

Suggested split:

- Calibration: older sessions through batch 01.
- Validation A: batch 02.
- Validation B: batch 03/newest sessions.
- Holdout: rows with high-confidence numeric geometry once extracted.

## Next Steps

1. Build the normalized decision-unit CSV and lock canonical enums.
2. Add machine-readable geometry fields where frame/OCR/OHLCV supports them.
3. Create the macro/news snapshot contract and backfill only cited news/calendar events.
4. Implement feature snapshots for BTC/ETH/SOL at each decision window.
5. Implement decision replay before full market backtest.
6. Run mismatch audit: every mismatch should become either a rule change, a feature gap, or a correct `unknown/hold`.

## Further Questions

- What exact news source should be considered the same information Craig had at the time?
- Should v1 try to reproduce only trade/no-trade actions first, or include management decisions in the first scoring pass?
- Should ambiguous multi-symbol rows be evaluated as exact symbol matches, or as acceptable candidate-set matches?
- How strict should the model be about Elliott/Fib automation before enough anchors exist?

## Source Artifacts

- `data/processed/gold_context_trades/gold_v03_trade_context_queue.csv`
- `data/processed/gold_context_trades/gold_v03_rule_seed_queue.csv`
- `data/processed/gold_context_trades/gold_v03_video_session_maps.csv`
- `data/processed/gold_context_trades/gold_v03_hold_context_queue.csv`
- `data/processed/gold_context_trades/gold_v03_quality_audit.csv`
- `data/processed/gold_context_trades/gold_v03_non_gold_recheck_audit.csv`
- `outputs/gold_v03_data_quality_profile_v1.json`
- `outputs/gold_v03_feature_audit_v1.csv`
