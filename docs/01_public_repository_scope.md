# Public Repository Scope

This repository is prepared as a portfolio-friendly public GitHub project. It is intentionally smaller than the local research folder.

## Included

- Project overview and workflow documentation.
- Source scripts that show the extraction, replay, feature, and audit logic.
- Public schemas and methodology files.
- Curated Markdown/YAML/JSON reports that explain results without requiring raw media.
- GitHub Actions syntax check for the Python scripts.

## Excluded

- Original video files and subtitles.
- Video frame captures, chart screenshots, and review workbook previews.
- YouTube metadata that contains temporary signed media URLs.
- The manual Excel workbook and generated review workbooks.
- Raw Binance/OHLCV caches and large audit tables.
- Parquet, ZIP, XLSX, NDJSON, log, and generated image files.
- Locally cloned third-party repositories.

## Rationale

The local workspace contains evidence and large generated artifacts that are useful for research but unsuitable for a public portfolio repository. Excluding them keeps the GitHub project:

- small enough to clone quickly;
- safer from copyright and privacy problems;
- easier for reviewers to understand;
- focused on the engineering process rather than raw source collection.

## Reproducibility Notes

The full pipeline expects local source files in paths such as `data/source/`, `data/raw/`, and local workbooks. Those folders are intentionally ignored by Git.

For a public reviewer, the repository should be evaluated as an engineering case study: how the workflow is structured, how lookahead leakage is avoided, how candidate decisions are audited, and how model evidence is separated from backtest output.

If the project later needs full reproducibility, use a separate private storage layer or GitHub Releases/Git LFS with explicit rights and a documented data manifest.
