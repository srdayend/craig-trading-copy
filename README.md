# Rule-Based Trading Decision Research

**Can discretionary trading decisions observed in public material be represented as timestamped rules and tested without using future information?**

This independent research project studies trading patterns associated with a third-party trader called Craig. The strategy concepts are **not claimed as my original trading ideas**. I built a workflow to organize source observations, define rule candidates, and audit whether a replay could have been made using information available at the time.

Python development was AI-assisted. The published results describe this rule implementation, not an estimate of the source trader’s performance.

## Approach

1. Organize documented examples into a small, reviewed **gold-context** dataset.
2. Separate thesis, candidate generation, and the actual timing of possible orders and fills.
3. Exclude information only known after a decision, including later candles and realized trade outcomes.
4. Replay entry, no-fill, cancel, stop, and exit cases with explicit rules.
5. Include fees, slippage, and conservative handling of ambiguous candles.

## What the prototype showed

The v1.2 event-driven execution prototype examined **1,390 accepted candidate cases**, of which **1,017 filled** under the model. The report records **negative net results (−468.746 total R)** after modeled costs, despite a positive gross total R before those costs.

This is **not a profitable or independently validated trading strategy**. The exercise made the effect of execution assumptions and fees visible and showed why an apparently repeatable pattern can fail when modeled as real orders.

[Read the event-driven test report](outputs/craig_v1_2_event_execution_report.md)

## Code and documentation

- [`docs/00_gold_context_workflow.md`](docs/00_gold_context_workflow.md) — source-evidence rules.
- [`docs/01_public_repository_scope.md`](docs/01_public_repository_scope.md) — files intentionally not published.
- [`scripts/`](scripts/) — feature extraction, candidate construction, replay, and audits.
- [`outputs/`](outputs/) — compact reports, rule files, and configurations.

Full reproduction requires local source material that is excluded from this public repo for copyright, privacy, and size reasons. Published reports are therefore **case-study evidence**, not a complete public dataset or a promise that anyone can reproduce all findings from this repo alone.

## Tech

Python, market-data preparation, rule-based modeling, replay simulation, auditable research reports; some workbook utilities use JavaScript.

**Independent research; not affiliated with or endorsed by Craig. No investment advice.**
