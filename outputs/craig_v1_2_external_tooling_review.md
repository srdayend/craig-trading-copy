# Craig v1.2 External Tooling Review

Generated for the v1.2 data expansion + HTF zone/trendline detector stage.

## Decision Summary

Craig v1.2 should use external tools only as transparent helpers. Craig DNA logic, thesis scoring, BTC PA context interpretation, target permission logic, no-chase/invalidation rules, and no-lookahead audit rules remain project-owned.

Chosen stack for this stage:

- Downloader: direct Binance Vision public zip downloader using the Python standard library.
- Data normalization and resampling: pandas + pyarrow/parquet.
- FVG, SR, swing, liquidity, and trendline logic: Craig-owned causal implementation.
- External SMC/trendline/backtest packages: research or validation helpers only, not production dependencies.

## Evaluation Table

| Area | Candidate | License / activity signal | No-lookahead / audit fit | Verdict |
| --- | --- | --- | --- | --- |
| Binance OHLCV | Binance Vision public data | Official Binance public market data; daily/monthly files are documented in [binance-public-data](https://github.com/binance/binance-public-data) and browsable at [data.binance.vision](https://data.binance.vision/) | Excellent. Raw zip files can be cached, checksummed later, and normalized with row-level source paths. | Adopt as primary source. |
| Binance OHLCV | Binance USD-M Futures REST klines | Official endpoint docs list `/fapi/v1/klines`, open-time identity, request weights, and max limit 1500 in [Binance developer docs](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) | Good fallback but slower and rate-limited. Raw response capture is needed for audit. | Keep as optional fallback only. |
| Binance OHLCV | Binance Python connector | Official SDK docs exist at [Binance Python Connectors](https://developers.binance.com/en/docs/sdks-tools/connectors/python) | Useful for API ergonomics, but it adds dependency surface without improving row-level audit over public zip files. | Do not add for this stage. |
| Multi-exchange OHLCV | CCXT | MIT, active, broad exchange support in [ccxt/ccxt](https://github.com/ccxt/ccxt) | Good portability, but unified APIs can hide venue-specific kline quirks unless raw responses are preserved. | Secondary adapter only, not used now. |
| Resample / feature store | pandas + pyarrow/parquet | Mature core Python data stack | Strong fit. Closed-candle resampling and audit columns are explicit and inspectable. | Adopt. |
| Large offline scans | Polars | Active columnar engine in [pola-rs/polars](https://github.com/pola-rs/polars) | Potential speedup, but resample parity tests would be required before replacing pandas. | Optional future acceleration. |
| Feature store infra | Feast | Active feature-store project in [feast-dev/feast](https://github.com/feast-dev/feast) | Too much serving/infrastructure overhead for deterministic local OHLCV features. | Reject for v1.2. |
| Swing pivots | stock-indicators Pivots | Documented pivot indicator in [stock-indicators docs](https://python.stockindicators.dev/indicators/Pivots/) | Pivot confirmation uses right-span bars; safe only if availability is delayed. | Use only as benchmark/test oracle. |
| SMC/FVG helpers | smartmoneyconcepts | Provides SMC-style pandas indicators in [rafalsza/smartmoneyconcepts](https://github.com/rafalsza/smartmoneyconcepts) | Definitions may use full-window context; row-level availability must be reimplemented anyway. | Reject for production logic. |
| Trendlines | trendln | MIT support/resistance trendline calculator in [GregoryMorse/trendln](https://github.com/GregoryMorse/trendln) | Useful visually, but full-chart trendline generation is repaint-prone without immutable line versions. | Exploratory helper only. |
| Trendlines | pytrendline | MIT; documented exhaustive scan in [ednunezg/pytrendline](https://github.com/ednunezg/pytrendline) | Can be non-causal if run over full history; cubic scanning is heavy for 1m/15m history. | Reject for core. |
| Backtest framework | NautilusTrader | Active event-driven framework in [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | Strong simulator, but heavy and can obscure Craig-specific audit semantics. | Possible external validation harness only. |
| Backtest framework | backtesting.py / vectorbt / backtrader | Useful projects but license/model concerns vary | Vectorized or generic trade APIs can make same-candle and no-chase audits harder. | Reject as v1.2 dependencies. |
| Reporting | Plotly, mplfinance, QuantStats | Widely used chart/report helpers | Fine if fed by Craig-owned rows with timestamps and object IDs. | Adopt later for visualization/reporting only. |

## Adopt / Non-Adopt Rationale

The implemented downloader uses Binance Vision files directly rather than a connector dependency because it preserves raw source files, has fewer moving parts, and makes re-runs deterministic. REST API fallback remains useful for missing or late daily chunks, but it should not be the primary path for multi-year 1m history.

Pattern-detection libraries are intentionally not adopted for production. The detector needs `available_at`, immutable trendline versions, delayed pivot confirmation, and event-time interactions. Those requirements are easier to audit in a small Craig-owned implementation than in a full-chart annotation library.

## Guardrail

Any future external helper must pass these gates before adoption:

- It can operate on already closed candles only.
- It exposes or allows reconstruction of row-level source timestamps.
- It does not backfill future-confirmed labels into earlier decision rows.
- It can be used as a helper without replacing Craig DNA scoring or trade-management logic.
- Its license is safe for local project use.
