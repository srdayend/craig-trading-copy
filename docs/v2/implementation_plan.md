# Craig v2 Implementation Plan

## Baseline boundary

Frozen comparison commit:

- 00ad3dbd75dc509a706fa594f4f821cc023ab1fa

Development branch:

- craig-v2-state-machine

## Reuse policy

Allowed reusable infrastructure:

- OHLCV loading and timestamp normalization.
- Closed-candle resampling.
- no-lookahead audit helpers.
- basic FVG and confirmed-swing primitives after independent tests.
- gold/context data readers.
- report formatting utilities.

Forbidden direct reuse in the v2 decision engine:

- v1.2 thesis score.
- v1.2 scenario priority and daily first-four selection.
- v1.2 confluence aggregation.
- v1.2 target-pool role selection.
- v1.2 sniper stop.
- v1.2 TP1-triggered BE.
- fixed 25/50/25 management.
- v1.2 S-tier/A-tier labels.

## Proposed package layout

- src/craig_v2/domain.py
- src/craig_v2/session.py
- src/craig_v2/zones.py
- src/craig_v2/scenarios.py
- src/craig_v2/entries.py
- src/craig_v2/management.py
- src/craig_v2/execution.py
- src/craig_v2/audit.py
- configs/craig_v2/baseline.yaml
- tests/craig_v2/
- outputs/v2/

## Initial implementation increments

### Increment 1: domain and state transitions

- Typed state enums and immutable event records.
- Reversal activation and invalidation.
- Continuation creation only after reversal failure.
- Zone freshness and repeated-mitigation state.
- Rule trace for every transition.

### Increment 2: 1m entry geometry

- Confirmed swing primitive.
- causal displacement leg.
- CHoCH/BOS event.
- 1m trendline-break interface, initially disabled unless validated.
- displacement-created FVG.
- midpoint limit lifecycle.
- no-chase cancellation.

### Increment 3: stop and BE

- Protected-swing, sweep, and FVG-candle anchors.
- explicit stop buffer.
- execution-cost-to-R guard.
- stored confirmation body level.
- body-close BE transition.

### Increment 4: structural targets

- Trigger-time target reconstruction.
- target ordering validation.
- all-out, partial-runner, and no-runner permissions.
- post-entry PA updates with event-time audit.

### Increment 5: execution and portfolio

- fill-candle ambiguity controls.
- realistic fee and slippage.
- one-position baseline.
- overlapping-position and repeated-entry control for SOLUSDT.
- daily risk state.

### Increment 6: evaluation

- deterministic unit scenarios.
- Craig session replay.
- continuous SOL backtest.
- walk-forward and holdout reports.
- ablation report for each added context family.

## Definition of done for the first executable baseline

- No v1.2 strategy-scoring imports.
- All state changes have rule traces.
- All features pass timestamp audit.
- 15m FVG may be a primary PA zone.
- Reversal failure can create, but cannot automatically enter, continuation.
- Every entry is tied to a stored scenario and zone.
- Every stop has a named 1m invalidation anchor.
- Every BE has a stored body-close confirmation level.
- Every target is directionally ordered after the actual entry.
- Gross and net expectancy per fill are separately reported.
- Same-candle ambiguity cannot create unearned target profits.
