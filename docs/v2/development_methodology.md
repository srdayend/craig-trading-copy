# Craig v2 Development Methodology

## 1. Objective hierarchy

Primary objective:

- Produce an independently testable rule-based strategy with positive out-of-sample expectancy after realistic execution costs.

Secondary objective:

- Preserve and measure similarity to Craig's causal decision process.

Non-objectives:

- Reproduce every public Craig trade.
- Maximize agreement by tuning thresholds to selected videos.
- Infer missing discretion from chart proxies.
- Treat Craig's public track record as a strategy backtest.

## 2. Evidence hierarchy

1. Owner strategy specification.
2. Complete continuous-market OHLCV and execution evidence.
3. Craig decision and management logs.
4. Targeted Craig video/frame review.
5. General trading literature and external hypotheses.

Higher-ranked evidence defines the strategy. Lower-ranked evidence may challenge it, but must not silently rewrite it.

## 3. Targeted video review

Video processing is not a default build stage.

A video segment is reviewed only when one of these conditions occurs repeatedly:

- v2 takes setups Craig consistently passes.
- v2 misses setups Craig consistently takes.
- side selection differs in the same market state.
- reversal-to-continuation transition differs.
- stop or BE timing differs.
- target and runner management differs.
- an undefined term blocks implementation.

Each review produces one of four outcomes:

- implementation bug
- specification ambiguity
- candidate missing hypothesis
- acceptable independent-strategy divergence

A candidate missing hypothesis is not added until it has an operational definition and survives ablation.

## 4. Build sequence

### Phase A: specification lock

- Review Strategy Spec v0.1.
- Resolve only decisions required for the minimum baseline.
- Version the result as v0.2.
- Freeze the initial holdout date range before performance iteration.

### Phase B: deterministic state engine

Implement independent state objects:

- SessionState
- ScenarioState
- ZoneState
- EntryState
- StopState
- BreakevenState
- TargetState

Do not import v1.2 thesis scoring, scenario ranking, target-selection, or management logic.

### Phase C: unit scenarios

Use small deterministic candle sequences to test:

- valid reversal
- reversal failure
- continuation retest
- no chase
- repeated mitigation rejection
- correct FVG midpoint order
- protected-swing stop
- body-close BE
- structural target update
- same-candle execution ambiguity

### Phase D: minimal continuous backtest

Initial baseline:

- SOLUSDT only
- limited PA-zone universe
- no Elliott proxy
- no automated discretionary trendline
- no fixed exit split
- realistic costs
- one position at a time

### Phase E: Craig session replay

Compare behavior without automatically changing rules.

Mismatch categories:

- session map
- primary symbol
- PA location
- side permission
- take/wait/pass/cancel
- entry geometry
- stop
- BE
- target/runner
- unknown evidence

### Phase F: hypothesis additions

Add one feature family at a time:

- BTC decisive-location context
- daily/4h bias
- session and volatility regime
- macro-event context
- validated trendlines
- manual wave/context filter

Every addition requires an ablation against the frozen baseline.

### Phase G: walk-forward and holdout

- Select parameters only on development and validation periods.
- Keep the holdout period untouched.
- Split Craig replay by session/video, never by random decision row.
- Report both fidelity and profitability; neither substitutes for the other.

## 5. Required metric separation

Fidelity metrics:

- action agreement
- side agreement
- primary-symbol agreement
- zone agreement
- entry-family agreement
- stop-anchor agreement
- BE timing agreement
- management agreement
- pass/no-trade recall

Strategy metrics:

- gross expectancy per fill
- net expectancy per fill
- candidate-to-order rate
- fill rate
- cost drag in R
- profit factor
- drawdown
- trade frequency
- regime stability
- largest-winner dependence
- overlapping exposure

## 6. Anti-overfitting rules

- No rule may be justified by one Craig example.
- No threshold may be changed only because the aggregate backtest improved.
- Every threshold change must show segment and walk-forward behavior.
- Unknown discretion remains unknown.
- Craig mismatches and profitability failures are logged separately.
- v1.2 results remain immutable.
