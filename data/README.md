# Data Directory

The public repository keeps only lightweight schemas and documentation.

Local research data is intentionally ignored:

- `data/source/`: downloaded videos, subtitles, frame captures, screenshots, metadata, and third-party reference repositories.
- `data/raw/`: OHLCV market-data caches.
- `data/processed/`: generated datasets and large review tables.

The one public exception is `data/processed/gold_context_trades/gold_trade_context_schema.md`, which documents the schema without publishing the underlying evidence rows.
