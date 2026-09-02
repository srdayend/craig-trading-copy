크레이그 트레이딩 카피 프로젝트에서 v0.3 gold context 추출과 v1 정규화 보강은 완료된 상태다.
이번 새 채팅의 목표는 바로 실전 자동매매가 아니라, Craig를 복제하기 위한 v1 rule engine / decision replay engine을 만드는 것이다.

현재 기준 산출물:

- `outputs/gold_v03_decision_units_v1.csv`
- `outputs/gold_v03_canonical_mapping_v1.csv`
- `outputs/gold_v03_v1_normalization_audit.md`
- `outputs/gold_v03_v1_model_eligibility_summary.json`
- `outputs/gold_v03_v1_ohlcv_coverage_manifest.csv`
- `outputs/gold_v03_craig_rule_model_v1_design.md`
- `outputs/gold_v03_feature_audit_v1.csv`

현재 데이터 상태:

- decision unit은 149행이고 `context_id` 중복은 없다.
- v0.3 trade context와 rule seed는 `context_id` 기준으로 완전 조인된다.
- 모든 decision unit의 frame evidence path가 존재한다.
- 모든 decision unit의 relevant symbol OHLCV coverage가 확보됐다. coverage manifest 기준 56개 date-symbol pair가 모두 `dated_file`이고 missing은 0이다.
- canonical 기준 `eligible_for_policy_learning=true`는 135행이다.
- exact/partial numeric geometry가 있는 `eligible_for_fill_backtest=true`는 8행뿐이다.
- management replay 가능 행은 38행이다.
- 대부분의 행은 `geometry_mode=frame_relative`이므로, exact fill/SL/TP 백테스트를 전체 행에 억지 적용하면 안 된다.
- outcome이 아직 `unknown`인 행은 16행이고, 이건 원천 정보 또는 결과 매칭이 부족한 것으로 유지해야 한다.
- raw label은 `decision_type_raw`, `direction_raw`, `symbol_raw`, `realized_result_raw`, `entry_price_raw`, `stop_price_raw`, `target_price_raw`에 보존되어 있다.

진행할 일:

1. 먼저 `gold_v03_decision_units_v1.csv`와 `gold_v03_canonical_mapping_v1.csv`를 읽고, canonical enum이 v1 rule engine에 충분한지 검토해라.
2. `needs_manual_review=true`인 mapping row 10개를 확인하되, 원본 의미를 바꾸지 말고 필요한 경우 별도 mapping v1.1 제안을 만들어라.
3. v1 engine의 런타임 입력을 정의해라. 런타임에는 Craig의 사후 설명문을 쓰면 안 되고, decision 시점까지의 OHLCV, 프레임/차트에서 정량화 가능한 구조, 당일 뉴스/매크로 캘린더만 써야 한다.
4. feature extractor를 설계하고 구현해라.
   - session phase
   - high-impact news proximity placeholder / join contract
   - BTC/ETH/SOL/ATOM relative strength
   - volatility regime
   - HTF bias/location
   - FVG candidate and freshness
   - CHoCH/BOS/displacement proxy
   - SR/flip/pivot cluster
   - trendline/channel proxy, 단 confidence 낮게
   - sweep/liquidity proxy
   - Elliott/Fib는 source row에서 명시된 경우 우선 label로 쓰고, 자동 검출은 별도 low-confidence feature로 분리
   - entry zone, invalidation, no-chase/cancel condition은 geometry confidence별로 분리
5. v1 rule engine은 다음 state machine으로 만들어라.
   - observe session state
   - form thesis
   - rank/select symbol
   - wait for setup
   - plan entry
   - wait for touch/fill
   - execute / no-fill / pass / cancel
   - manage risk
   - exit / hold / unknown
6. backtest/replay는 세 층으로 분리해라.
   - policy replay: `eligible_for_policy_learning=true` 135행에서 Craig가 take/wait/pass/cancel/no-fill/management 중 무엇을 했는지 재현
   - exact fill replay: `eligible_for_fill_backtest=true` 8행에서만 candle fill/SL/TP를 시뮬레이션
   - management replay: `eligible_for_management_replay=true` 38행에서 BE/risk reduction/runner/manual exit logic을 검증
7. unknown/hold/context-only 행을 실패로 취급하지 말고, exclusion 또는 session prior evidence로 분리해라.
8. 최종 산출물은 아래처럼 만들어라.
   - `outputs/craig_v1_rulebook.yaml`
   - `scripts/build_craig_v1_features.py`
   - `scripts/run_craig_v1_decision_replay.py`
   - `outputs/craig_v1_feature_matrix.csv`
   - `outputs/craig_v1_replay_results.csv`
   - `outputs/craig_v1_validation_report.md`

중요 원칙:

- 원본 gold context의 의미를 바꾸지 마라.
- 숫자 entry/SL/TP가 없는 row에 임의 숫자를 만들지 마라.
- `frame_relative` row는 구조/정책 학습에는 쓰되 exact PnL backtest에는 쓰지 마라.
- 사후 결과를 feature로 쓰는 lookahead leakage를 만들지 마라.
- 뉴스/매크로는 아직 normalized external table이 없으므로, 우선 join contract와 placeholder feature를 만들고 실제 뉴스 캘린더 보강은 별도 단계로 분리해라.
- 최종 목표는 수익 최적화가 아니라 “Craig가 같은 조건에서 왜 그 판단을 했는지”를 재현하는 것이다.
