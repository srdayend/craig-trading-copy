# Craig Trading Copy Research

Rule-based research workspace for turning Craig-style live trading observations into auditable decision logic.

This project is not a trading bot and is not investment advice. The goal is to reconstruct decision context from source evidence, promote only high-confidence examples into a gold dataset, and test whether those rules can be replayed without lookahead leakage.

## Project Goal

The core question is:

> Given only the information available before or during a trading decision, can a rule engine reproduce the same kind of take, wait, pass, cancel, no-fill, manage, or exit decision?

The project is organized around three principles:

- Keep the dataset small, but evidence-backed.
- Separate Craig-imitation replay from independent strategy backtesting.
- Never use future candles, realized outcome, or post-trade explanation as model input.

## Current Status

- Gold-context workflow is defined.
- Trade context schema is documented.
- v1 decision replay and v1.1 mismatch calibration reports exist.
- v1.2 architecture separates thesis, target pools, candidate generation, event-driven fills, and Craig-DNA audit.
- Raw video files, subtitles, screenshots, extracted frames, downloaded market caches, and manual workbooks are intentionally excluded from the public repository.

## Repository Structure

| Path | Purpose |
|---|---|
| `scripts/` | Python and Node scripts for extraction, feature generation, replay, workbook generation, and audits. |
| `docs/00_gold_context_workflow.md` | Evidence standard for promoting a trade/setup/pass into the gold dataset. |
| `docs/01_public_repository_scope.md` | What is included in GitHub and what stays local. |
| `docs/SCRIPT_INDEX.md` | Human-readable map of the script groups. |
| `data/processed/gold_context_trades/gold_trade_context_schema.md` | Public schema for the gold trade-context table. |
| `outputs/` | Curated text reports and rule/config files only. Heavy generated data is ignored. |
| `PROJECT_CONTEXT.md` | Working context used while continuing the research. |

## Included Report Examples

- `outputs/gold_v03_craig_rule_model_v1_design.md`
- `outputs/craig_v1_validation_report.md`
- `outputs/craig_v1_1_validation_report.md`
- `outputs/craig_v1_2_dna_locked_backtest_architecture.md`
- `outputs/craig_v1_2_event_execution_report.md`
- `outputs/gold_v03_v1_normalization_audit.md`

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m compileall -q scripts
```

Some scripts require local-only source assets that are not stored in GitHub. See `docs/01_public_repository_scope.md` before trying to reproduce full outputs.

The `.mjs` workbook scripts were built for the Codex desktop spreadsheet artifact runtime and may need that environment or equivalent package access.

## Data Policy

The public repository keeps methodology, code, schemas, and compact reports. It does not publish:

- downloaded YouTube videos or subtitles;
- frame captures or chart screenshots;
- temporary YouTube media URLs;
- manual Excel notes;
- raw OHLCV market-data caches;
- large generated CSV, Parquet, XLSX, image, archive, or log files;
- cloned third-party repositories used only for local reference.

## License

No open-source license has been selected yet. The repository is published for portfolio review and discussion, not for unrestricted reuse.
