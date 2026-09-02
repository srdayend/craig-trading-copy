# Craig-Inspired Strategy Specification v0.1

Status: Draft for owner review  
Development branch: craig-v2-state-machine  
Frozen v1.2 baseline commit: 00ad3dbd75dc509a706fa594f4f821cc023ab1fa

## 1. Authority and objective

This specification is the primary design authority for v2.

The primary objective is to build a Craig-inspired, rule-based strategy with independently positive out-of-sample expectancy after realistic costs.

Craig videos and trade logs are secondary evidence. They may be used to audit fidelity, diagnose repeated mismatches, and discover missing hypotheses. They must not silently override this specification or be used as a direct profitability target.

v1.2 is preserved as a historical research pipeline and failure baseline. v2 must not incrementally mutate v1.2 strategy logic.

## 2. Core decision chain

The intended causal chain is:

1. Build the daily/HTF market map.
2. Determine BTC relevance and directional context.
3. Select the primary trading symbol.
4. Identify reachable 15m price-action zones and conditional scenarios.
5. Track the active zone state.
6. Decide whether the active hypothesis is reversal or continuation.
7. Require a qualifying 1m structure shift and displacement-created FVG.
8. Enter only on the FVG midpoint retrace.
9. Place the stop at a real 1m thesis-invalidation anchor.
10. Move to breakeven only after the entry thesis receives body-close confirmation.
11. Manage targets using newly available market structure.

A valid 1m pattern is never sufficient without an active higher-timeframe scenario and price-action location.

## 3. Rule confidence classes

### 3.1 Hard rules

Hard rules are deterministic requirements for the initial strategy.

- The baseline trading symbol is SOLUSDT until symbol-selection logic is separately validated.
- BTCUSDT is context, not a blindly copied directional signal.
- Primary execution timeframe is 1m.
- Primary intraday price-action timeframe is 15m.
- Entry requires an active or reached price-action zone.
- Entry requires a 1m displacement leg that creates an FVG.
- The displacement leg must create either a qualifying CHoCH/BOS or a qualifying 1m trendline break.
- Entry is a limit order at the 1m FVG midpoint.
- No market chase is allowed after the planned midpoint entry is missed.
- Stop placement must be tied to the 1m setup invalidation, not chosen to manufacture high R.
- Breakeven is triggered by a qualifying 1m body close beyond the stored confirmation level, not by an arbitrary fixed-R target.
- Planned targets must come from visible structure. Fixed-R may be reported but is not the primary target source.
- All features and state changes use only information available at the decision timestamp.

### 3.2 Soft context

Soft context changes side permission, confidence, position size, target ambition, or counter-trend conservatism. It does not independently create an entry.

- Daily and 4h directional pressure.
- Major HTF support, resistance, SR flip, FVG, and trendline context.
- BTC at a decisive level versus BTC in non-decisive chop.
- Macro and scheduled event regime.
- Expected daily range and reachable zones.
- Counter-bias versus aligned-bias trade.
- Session phase and volatility regime.
- Relative strength and setup cleanliness across symbols.
- Strength and freshness of the current 15m PA reaction.
- Density of opposing structure before the target.

### 3.3 Unknown or manual-only context

These items must remain unknown, disabled, or manually annotated until a defensible operational definition exists.

- Elliott wave 3/5/ABC counts.
- Subjective hand-drawn trendlines that cannot be reconstructed reliably.
- Visual assessments such as clean structure without an agreed definition.
- Unstated Craig intuition.
- Exact macro interpretation not recoverable from a timestamped source.
- Exact position-sizing changes unless a risk rule is explicitly defined.

Unknown context must never be replaced automatically by an invented proxy.

## 4. State model

### 4.1 SessionState

Minimum fields:

- session_id
- session_date
- session_timezone_definition
- primary_symbol
- btc_relevance: decisive, contextual, neutral
- bias_side: long, short, neutral, open_ended
- bias_strength: weak, medium, strong
- macro_regime: normal, scheduled_event, post_event, unknown
- volatility_regime
- active_scenario_ids
- completed_trade_count
- realized_daily_r
- risk_permission

The session state is persistent. It must not be rebuilt as an unrelated score on every 15m candle.

### 4.2 ScenarioState

A scenario represents a conditional hypothesis, not a prediction.

Minimum scenario families:

- reversal_at_pa
- continuation_after_pa_failure
- no_trade_chop

Minimum fields:

- scenario_id
- side
- scenario_family
- activation_conditions
- invalidation_conditions
- primary_zone_id
- btc_permission
- bias_alignment
- state: planned, approaching, active, confirmed, invalidated, completed

Reversal and continuation are linked:

- A reversal scenario becomes active when price reaches or sweeps the intended PA zone.
- If the expected reversal response fails and price accepts through the zone, the reversal scenario is invalidated.
- A continuation scenario may then be created, but entry still requires a fresh corrective 1m reversal and FVG midpoint retrace.

### 4.3 ZoneState

Minimum states:

- fresh
- approaching
- touched
- swept
- rejected
- accepted_through
- invalidated
- consumed

A repeated touch does not reset freshness indefinitely. Repeated mitigation must reduce setup permission unless a new scenario explicitly restores it.

Initial PA-zone universe:

- PDH and PDL.
- Reachable 15m FVGs existing before the session decision.
- New 15m FVGs formed during the session.
- Explicit 15m/1h/4h SR or SR flip zones.
- Validated HTF trendline zones.
- Other liquidity zones only after their definition is validated.

Confluence must be spatial and event-time aligned. Separate high scores at different prices or times do not count as confluence.

### 4.4 EntryState

Required event sequence:

1. The active scenario permits a side.
2. Price reaches or interacts with the primary PA zone.
3. A 1m structure shift occurs in the permitted direction.
4. The shift includes directional displacement.
5. The displacement creates a 1m FVG.
6. A limit order is placed at the FVG midpoint.
7. The order fills, expires, or is canceled by no-chase/invalidation.

The CHoCH/trendline-break event and the FVG may occur across the same causal displacement leg; they are not required to be the exact same candle.

The engine must store:

- protected_swing_level
- structure_break_level
- displacement_start_time
- displacement_end_time
- fvg_low
- fvg_high
- fvg_mid
- confirmation_body_level
- order_expiry_reason
- no_chase_reason

### 4.5 StopState

Allowed initial stop families:

- beyond the displacement/FVG-creation candle.
- beyond the protected 1m swing.
- beyond the sweep high or low.
- a small explicit buffer beyond the chosen invalidation anchor.

The hierarchy among these anchors is TBD and requires owner review.

Rejected stop designs:

- entire HTF zone boundary used automatically for a 1m setup.
- recent arbitrary N-bar extreme with no structural meaning.
- stop selected to maximize planned R.
- stop with expected execution costs too large relative to 1R.
- future swing used as an anchor.

### 4.6 BreakevenState

Breakeven is not tied to TP1.

At entry creation, the engine must store the exact confirmation body level associated with the displacement/structure shift.

For a long:

- move the stop to entry only after a completed 1m candle body closes beyond the qualifying bullish confirmation level.

For a short:

- move the stop to entry only after a completed 1m candle body closes below the qualifying bearish confirmation level.

The exact definition of the confirmation body level is TBD and must be resolved with chart examples before implementation is finalized.

### 4.7 TargetState

Pre-entry target candidates:

- next relevant 15m opposing PA zone.
- PDH/PDL or current session extreme when structurally valid.
- 1h/4h opposing PA zone.
- strong validated 1m resistance/support when used as an all-out target.
- visible liquidity draw.

Targets must be rebuilt at trigger time. They may be revised after entry only when a new structure becomes available, with a timestamped management trace.

The initial version must not impose a fixed 25/50/25 exit split.

Management modes:

- all_out_at_structural_target
- partial_then_runner
- runner_not_permitted
- manual_or_structural_flat

Exact allocation and runner rules are TBD.

## 5. Bias behavior

Bias is permission and management context, not an entry signal.

- Aligned-bias trades may receive normal target and runner permission.
- Counter-bias trades require stronger PA evidence.
- Counter-bias trades may use smaller size, earlier all-out targets, or no runner.
- Strong BTC contradiction may veto an alt trade only when BTC is at a genuinely decisive PA location.
- BTC mid-range chop should be neutral rather than forced into bullish or bearish context.

The exact size and target modifiers are TBD.

## 6. No-trade and cancellation behavior

The system must treat not trading as an explicit decision.

Initial negative states:

- no_valid_session_map
- no_reachable_pa_zone
- middle_of_range_chop
- btc_decision_pending
- repeated_zone_mitigation
- reversal_failed_wait_for_continuation_retest
- no_valid_1m_structure_shift
- fvg_not_created_by_displacement
- missed_entry_no_chase
- rr_compressed_after_move
- costs_too_large_relative_to_risk
- target_path_blocked
- unsupported_discretionary_context

## 7. Execution requirements

- Use a realistic fee and slippage model.
- Report gross and net expectancy per candidate, order, and fill separately.
- Validate target ordering after actual entry construction.
- Rebuild target candidates at the trigger timestamp.
- Do not award target touches that may have occurred before a same-candle limit fill.
- Use tick/sub-minute data where available; otherwise report conservative and optimistic intrabar bounds.
- Model correlated exposure and overlapping positions before reporting an account equity curve.

## 8. Validation hierarchy

### 8.1 Specification tests

Hand-built deterministic chart cases must verify every state transition.

### 8.2 Craig session replay

Craig sessions measure:

- session bias agreement
- primary symbol agreement
- PA-zone agreement
- take/wait/pass/cancel agreement
- side agreement
- trigger-family agreement
- stop-anchor agreement
- BE timing agreement
- target/runner management agreement

A Craig mismatch is diagnostic evidence, not automatic proof that v2 is wrong.

### 8.3 Continuous-market backtest

Profitability must be measured on complete continuous market data, not selected Craig videos.

Required reporting:

- gross and net expectancy per fill
- profit factor
- drawdown
- trade frequency
- cost drag in R
- no-fill and no-chase rates
- mode and regime segments
- largest-winner dependence
- overlapping exposure
- walk-forward and untouched holdout results

## 9. Change-control rule

Every new rule must have:

- a stated causal hypothesis
- an operational definition
- a source class: owner specification, market-data hypothesis, repeated Craig mismatch, or external evidence
- a timestamp-safe implementation
- an ablation result
- a versioned change note

A single Craig trade or a single profitable backtest example is insufficient justification for a new rule.

## 10. Open decisions for v0.2

- Exact session timezone and PDH/PDL boundary.
- Whether v0.1 remains SOL-only or includes a minimal symbol selector.
- Formal definition of a reachable 15m PA zone.
- Formal acceptance/failure rule for reversal-to-continuation transition.
- Strict CHoCH/BOS swing definition.
- Valid 1m trendline definition.
- Stop-anchor hierarchy.
- Exact BE confirmation body level.
- No-chase expiry and distance.
- Minimum structural RR and maximum execution-cost-to-R.
- Partial/all-out/runner allocation rules.
- Macro-event source and manual versus automated interpretation.
