# PROJECT CONTEXT

## Objective

Build a rule-based Craig trading copy model from a small but high-quality source set.

The source set must contain only events whose relevant context can be reconstructed. Executed trades are useful when entry reason, setup, execution, management, and result are visible or directly stated. Unfilled or canceled setups are also useful when Craig fully specified the thesis, entry, stop, and target before fill.

## Current Instruction

Use the user's manual workbook as the detail standard, but do not preserve the loose writing style. Convert it into a cleaner rule-building structure while keeping the same level of nuance:

- Craig's pre-trade thesis and higher-timeframe reasoning.
- Multiple intentions and thought changes before entry.
- Reasons for waiting, passing, canceling, retrying, or becoming conservative.
- Exact setup structure: reaction zone, FVG, CHoCH, trendline, SR flip, fib/wave, pair comparison, session context.
- Fill, stop, target, BE, trailing, manual close, and final result for executed trades.
- For unfilled setups, the complete pre-fill setup is enough if thesis, entry, stop, and target are all explicit.

Do not promote inferred or incomplete events into the gold dataset.

## Preserved Sources

- `크레이그 매매 수동 저장파일.xlsx`
- `data/source/craig_youtube/transcripts/`
- `data/source/craig_youtube/details.json`
- `data/raw/`
- `data/source/craig_frames/`
- `scripts/`

## Active Outputs

- `data/processed/gold_context_trades/manual_seed_contexts.csv`
- `data/processed/gold_context_trades/review_scope_bdg_forward.csv`
- `docs/00_gold_context_workflow.md`
- `outputs/gold_context_work_log.md`

## Archived Legacy Work

Old docs and broad candidate outputs were moved to:

`archive/legacy_pre_gold_context_20260823_014050/`

They should not be used as methodology or answer keys for the new workflow. Use them only if a raw source pointer must be recovered.
