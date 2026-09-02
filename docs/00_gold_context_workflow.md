# Gold Context Workflow

## Principle

The dataset should be smaller and cleaner than a complete trade list.

The rule model should learn only from events where Craig's context is recoverable without guessing.

This includes:

- Executed trades with setup, fill, management, and result.
- Fully specified actionable setups that did not fill, if Craig stated or showed the thesis, entry, stop, and target.
- Explicit pass decisions when the reason for passing is clear enough to become a rule.

Unclear, recap-only, or visually ambiguous events can be logged, but they should not become rule evidence unless the missing pieces are recovered.

## Trade Status

| Status | Meaning | Can Train Rules? |
|---|---|---|
| `gold_executed_trade` | Entry reason, setup, execution, management, result, and source anchors are all secured. | Yes |
| `gold_actionable_setup` | Thesis, setup, entry, stop, target, and no-fill/cancel result are secured. | Yes |
| `gold_pass_rule` | Craig explicitly passed or canceled and the reason is clear enough to model. | Yes, as a filter/pass rule |
| `needs_frame_review` | Transcript has enough context, but direction/entry/SL/TP/fill/result needs visual confirmation. | No |
| `needs_recap_match` | Setup and execution are visible, but final result must be matched to recap/journal. | No |
| `context_incomplete` | Some context exists, but a required part is missing. | No |
| `pass_or_missed` | Craig discussed or prepared it but did not take a usable trade. | No |
| `discard` | Not useful for this workflow. | No |

## Required Fields For Executed Trade Gold

1. Source identity: video id, link, video timestamp, market date if available.
2. Trade identity: symbol, direction, trade number or local sequence.
3. Pre-entry thesis: the larger reason this area matters.
4. Intention timeline: Craig's changing thoughts before entry.
5. Setup structure: reaction zone, trigger, entry plan, SL logic, target logic.
6. Execution: filled, partially filled, missed, canceled, or re-entered.
7. Management: BE move, risk reduction, trailing, add/remove decisions.
8. Result: TP, stop, BE, manual close, missed full move, or canceled.
9. Evidence anchors: transcript time anchors plus frame/recap anchors where needed.
10. Confidence note: what is certain, what was visually verified, and what remains unresolved.

## Required Fields For Actionable Setup Gold

1. Source identity: video id, link, video timestamp, market date if available.
2. Trade identity: symbol, direction, local sequence if clear.
3. Pre-entry thesis: the larger reason this area matters.
4. Intention timeline: why Craig wants this setup now and what would invalidate it.
5. Setup structure: reaction zone, trigger, entry plan, SL logic, target logic.
6. Execution state: missed fill, canceled, no trigger, or price ran away.
7. Evidence anchors: transcript time anchors plus chart/position-box frames.
8. Confidence note: why this is complete enough to train the entry/setup rules despite no fill.

## Review Loop

1. Extract candidate event windows from transcript.
2. Read the transcript before and after the candidate window.
3. Watch or inspect frames around setup, entry, management, and recap.
4. Confirm position box/order panel when entry, SL, TP, or direction is not verbally explicit.
5. Match the event to recap/journal so trade count and result are consistent.
6. Promote only complete events into `gold_executed_trade`, `gold_actionable_setup`, or `gold_pass_rule`.
7. Leave ambiguous trades outside the rule dataset.

## Notes For Rule Building

Keep nuanced reasoning. Craig often changes plan because a wave may extend, a retest comes too late, the pair relationship changes, a level is too close, or the session becomes choppy. These are not noise. They are rule features.

When writing final notes, prefer structured fields over long prose, but do not compress away the decision process.
