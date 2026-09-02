# Final Context Master v0.2

이 파일은 현재 방식의 통합 산출물이다. 이미 시각 검토한 bDg/파일럿3와, 남은 영상 전체의 자동 review queue를 같은 스키마로 합쳤다.

중요: `remaining_auto_queue` 행은 최종 gold가 아니라 누락 방지용 후보이며, `final_gold_ready_candidates_v0_2.csv`만 바로 룰 증거 후보로 보는 것이 안전하다.

시간 원칙: `market_time_utc_minus4`는 수동 엑셀/하단축/OHLCV 정렬처럼 실제로 확보된 시각만 넣는다. 자막에서 들린 시각은 `market_time_hint_utc_minus4`에만 보관한다.

- master rows: 232
- visual/manual ready rows: 41
- rows with market date present: 231
- rows with secured UTC-4 market time: 15
- rows with spoken/session time hint only: 74

## Source Stage Counts

- bDg_visual_review: 8
- manual_seed: 16
- pilot3_visual_review: 20
- remaining_auto_queue: 188

## Evidence Status Counts

- auto_context_candidate_needs_review: 2
- auto_executed_trade_review_candidate: 186
- context_incomplete_not_gold: 2
- gold_actionable_setup_candidate: 5
- gold_executed_trade_candidate: 18
- gold_pass_rule_candidate: 2
- needs_frame_review: 16
- not_gold_context_incomplete: 1

## Market Time Confidence

- high: 15
- not_available: 217

## Spoken Time Hint Confidence

- medium: 23
- low: 51
- blank: 158

## Files

- master: `data/processed/gold_context_trades/final_context_master_v0_2.csv`
- gold-ready subset: `data/processed/gold_context_trades/final_gold_ready_candidates_v0_2.csv`
- remaining frame plan: `data/processed/gold_context_trades/remaining_frame_capture_plan_v0_2.csv`
