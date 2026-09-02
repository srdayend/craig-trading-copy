# Craig gold v0.3 to v1 decision-unit normalization audit

Generated: 2026-08-24T16:37:27

## What changed

- Kept the original v0.3 gold rows unchanged.
- Added a derived v1 decision-unit layer with canonical decision, direction, outcome, geometry, time, OHLCV, and eligibility fields.
- Preserved raw labels in `decision_type_raw`, `direction_raw`, `symbol_raw`, `realized_result_raw`, and raw price fields.
- Rechecked local OHLCV file coverage after the missing-date fetch step.
- Did not infer numeric entry/SL/TP where source geometry is only frame-relative or prose.

## Row counts

- Decision units: 149
- External hold rows kept outside gold: 5
- Raw decision_type distinct: 90
- Raw direction distinct: 26
- Raw symbol distinct: 8

## Canonical decision_class

- `executed_trade`: 99
- `actionable_setup`: 14
- `session_context`: 9
- `planned_no_fill`: 7
- `pass_cancel`: 7
- `process_rule_context`: 5
- `conditional_setup`: 4
- `management_context`: 4

## Canonical outcome_class

- `win`: 54
- `loss`: 25
- `breakeven`: 20
- `unknown`: 16
- `context_only`: 14
- `no_fill`: 8
- `mixed`: 5
- `pass`: 4
- `cancelled`: 3

## Geometry readiness

- `frame_relative`: 136
- `numeric_exact`: 6
- `prose_only`: 5
- `numeric_partial`: 2

- Numeric entry rows: 9
- Numeric stop rows: 7
- Numeric target rows: 7

## OHLCV coverage

- `covered_all_relevant_symbols`: 149

## Model eligibility

- `true`: 135
- `false`: 14

Fill backtest:

- `false`: 141
- `true`: 8

Management replay:

- `false`: 111
- `true`: 38

## Remaining data limits

- Most rows are still relative-structure/prose geometry; exact fill/SL/TP simulation must stay limited to `geometry_mode in {numeric_exact,numeric_partial}`.
- A canonical enum can now be consumed by v1, but rows marked `needs_manual_review=true` in the mapping file should be reviewed before freezing a permanent ontology.
- News/macro calendar data is still not a normalized external table. Rows can expose macro/news tags, but the next model stage should join an external same-day calendar before claiming true Craig-like inputs.
- ATOM appears as a non-core symbol; BTC/ETH/SOL coverage is fixed, but ATOM-specific OHLCV remains out of scope unless separately fetched.

## Output files

- `outputs\gold_v03_decision_units_v1.csv`
- `outputs\gold_v03_canonical_mapping_v1.csv`
- `outputs\gold_v03_v1_model_eligibility_summary.json`
- `outputs\gold_v03_v1_normalization_audit.md`
- `outputs\gold_v03_v1_ohlcv_coverage_manifest.csv`
