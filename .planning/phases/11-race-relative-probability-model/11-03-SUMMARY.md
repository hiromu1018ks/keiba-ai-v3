---
phase: 11-race-relative-probability-model
plan: 03
subsystem: model
tags: [model, orchestrator, integration, artifact, race-relative, wave2, model-01, safe-01, d-01, d-06, d-10, sc3, sc4, sc5]

# Dependency graph
requires:
  - "11-01 Wave 0 race_relative.py stub + test 契約（定数事前登録）"
  - "11-02 Wave 1 race_relative.py 3 公開関数実装（apply_race_relative_correction）"
  - "src/model/orchestrator.py train_and_predict（行整列保証・aligned pred_proba 注入・Cycle 2 NEW HIGH-1）"
  - "src/model/artifact.py save_native_artifact（base+calibrator 分離保存・metadata.json）"
  - "src/model/predict.py make_model_version + MODEL_TYPE_TO_SHORT"
provides:
  - "orchestrator.train_and_predict が theta + score_split 引数を取り・theta=None で v1.0 等価（A5 後方互換）"
  - "_normalize_model_type helper（lightgbm_rr→lightgbm / catboost_rr→catboost・codex HIGH#2）"
  - "theta/model_type 双方向 guard（codex cycle-2 MEDIUM・silent provenance hole 回避）"
  - "score_split='calib' で θ 選択経路が test 窓に触れない構造的聖域ブロック（codex HIGH#1・§11.2）"
  - "sales_start_entry_count を必須取得・fallback なし（codex HIGH#6・D-08/D-09）"
  - "race_relative.apply_race_relative_correction が LightGBM/CatBoost 両予測パスに挿入（SC#3 bit-identical）"
  - "戻り値 dict に race_relative_theta / score_split provenance（§19.1）"
  - "artifact.save_native_artifact metadata.json に theta provenance（race_relative_theta / xtol / epsilon）"
  - "predict.make_model_version が lightgbm_rr→lgbrr / catboost_rr→cbrr をサポート"
  - "scripts/run_train_predict.py が race_relative_theta を result から渡す（codex MEDIUM）"
affects:
  - "11-04（run_phase11_evaluation.py が本 orchestrator 拡張を消費・θ 選択経路で score_split='calib' を使用）"
  - "11-05（live-DB SC#2/SC#3/SC#5 検証・model_version で binary と race-relative を並列保存）"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "score_split 引数による構造的聖域ブロック（docstring でなく API seam で §11.2 を機械保証）"
    - "_normalize_model_type で binary base / race-relative original を分離（学習は base・version 採番は original）"
    - "theta/model_type 双方向 guard（冒頭配置で feature_df 無しでも発火・silent provenance hole 回避）"
    - "sales_start_entry_count 必須取得 + race 内一意性 guard（D-08/D-09 singleton 一意性）"
    - "race-relative theta provenance を metadata.json に記録（α_r は不保存・D-10 自己完結性）"
    - "定数値を数値リテラルで metadata に直接記述（循環 import 回避・bit-identical 保証）"

key-files:
  created: []
  modified:
    - "src/model/orchestrator.py（theta/score_split 引数・_normalize_model_type・双方向 guard・補正層挿入・provenance）"
    - "src/model/artifact.py（save_native_artifact に race_relative_theta 引数・metadata.json 拡張）"
    - "src/model/predict.py（MODEL_TYPE_TO_SHORT に lightgbm_rr/catboost_rr 追加）"
    - "scripts/run_train_predict.py（save_native_artifact 呼出に race_relative_theta=result.get(...) 追加）"

key-decisions:
  - "_normalize_model_type は module-level helper として配置（train_and_predict 直前・codex HIGH#2）"
  - "theta/model_type 双方向 guard は train_and_predict 冒頭に配置（feature_df 無しでも発火・codex cycle-2 MEDIUM）"
  - "score_split='calib' の race_df_score は calib_df.loc[X_calib.index, :] から構築（splits['calib'] と整合）"
  - "sales_start_entry_count は race_df_score から必須取得・race 内一意性 guard・groupby-size fallback なし（codex HIGH#6）"
  - "race_relative の定数（xtol=1e-9 / epsilon=1e-6）は metadata.json に数値リテラルで記述（race_relative.py と一致・docstring 明記・循環 import 回避）"
  - "α_r 自体は metadata に保存しない（D-10 自己完結性・θ + base logit + k から brentq で完全再現）"
  - "両モデルで同一の apply_race_relative_correction を呼ぶ（SC#3 bit-identical・D-01 binary 本体不変）"

patterns-established:
  - "score_split による予測対象の切替（X_score / race_df_score）・test/calib 両方で行整列 assert を保持"
  - "theta=None で補正層スキップ・theta=float で補正層適用（A5 後方互換）"
  - "race-relative model_version 採番（-lgbrr-v1 / -cbrr-v1 で binary と区別）"
  - "theta provenance を metadata.json に記録（§19.1 再現性）"

requirements-completed:
  - MODEL-01
  - SAFE-01

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "orchestrator.train_and_predict が theta + score_split + _normalize_model_type を持つ（codex HIGH#1/#2・A5 後方互換）"
    requirement: "MODEL-01"
    verification:
      - kind: unit
        ref: "tests/model/test_orchestrator.py（既存7テスト全 GREEN・theta=None/score_split=test で v1.0 等価・SC#4 回帰防止）"
        status: pass
      - kind: unit
        ref: "uv run python -c \"import inspect; from src.model.orchestrator import train_and_predict, _normalize_model_type; sig=inspect.signature(train_and_predict); assert 'theta' in sig.parameters; assert 'score_split' in sig.parameters; assert _normalize_model_type('lightgbm_rr') == ('lightgbm','lightgbm_rr')\""
        status: pass
    human_judgment: false
  - id: D2
    description: "theta/model_type 双方向 guard が silent provenance hole を構造的ブロック（codex cycle-2 MEDIUM）"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "uv run python guard 検証スクリプト（theta=float + lightgbm → ValueError / lightgbm_rr + theta=None → ValueError / bad score_split → ValueError）"
        status: pass
    human_judgment: false
  - id: D3
    description: "score_split='calib' で θ 選択経路が test 窓に触れない構造的聖域ブロック（codex HIGH#1・§11.2）"
    requirement: "SAFE-01"
    verification:
      - kind: unit
        ref: "src/model/orchestrator.py の score_split guard と X_score/race_df_score 切替ロジック（grep検証済）"
        status: pass
    human_judgment: false
  - id: D4
    description: "sales_start_entry_count を race_df から必須取得・groupby-size fallback なし（codex HIGH#6）"
    requirement: "MODEL-01"
    verification:
      - kind: unit
        ref: "uv run python -c \"import inspect, re; from src.model import orchestrator as o; src=inspect.getsource(o); assert 'sales_start_entry_count' in src; assert not re.search(r'groupby\\([^)]*\\)\\.size\\(\\)|\\.size\\(\\).*fallback|len\\([^)]*group', src)\""
        status: pass
    human_judgment: false
  - id: D5
    description: "両モデル（LightGBM/CatBoost）で同一の apply_race_relative_correction を呼ぶ（SC#3 bit-identical）"
    requirement: "MODEL-01"
    verification:
      - kind: unit
        ref: "src/model/orchestrator.py の theta is not None ブロックで base_model_type に依存せず共通補正層を呼出（grep 'apply_race_relative_correction' で確認）"
        status: pass
    human_judgment: false
  - id: D6
    description: "artifact metadata.json に theta provenance 追加・α_r は不保存（D-10）・scripts/run_train_predict.py が渡す（codex MEDIUM）"
    requirement: "MODEL-01"
    verification:
      - kind: unit
        ref: "uv run python で write_metadata_json による metadata.json roundtrip 検証（race_relative_theta=0.75 / xtol=1e-9 / epsilon=1e-6・byte-reproducible・alpha_r 不保存）"
        status: pass
      - kind: unit
        ref: "grep -c 'race_relative_theta=result.get' scripts/run_train_predict.py == 1"
        status: pass
    human_judgment: false
  - id: D7
    description: "predict.make_model_version が race-relative short 識別子（lightgbm_rr→lgbrr / catboost_rr→cbrr）をサポート"
    requirement: "MODEL-01"
    verification:
      - kind: unit
        ref: "uv run python -c \"from src.model.predict import make_model_version; assert make_model_version('20260626-1a-opponentstrength-v1', 'lightgbm_rr', 1) == '20260626-1a-opponentstrength-v1-lgbrr-v1'; assert make_model_version('20260626-1a-opponentstrength-v1', 'catboost_rr', 1) == '20260626-1a-opponentstrength-v1-cbrr-v1'\""
        status: pass
    human_judgment: false

# Metrics
duration: 8 min
completed: 2026-06-27
status: complete
---

# Phase 11 Plan 03: Orchestrator theta + score_split 統合 + artifact/predict 拡張 Summary

orchestrator.train_and_predict に Phase 11 race-relative 補正層（theta + score_split + _normalize_model_type・双方向 guard・sales_start_entry_count 必須）を統合し・artifact.save_native_artifact の metadata.json に theta provenance を追加・predict.make_model_version が race-relative short（lgbrr/cbrr）をサポート。theta=None で v1.0 binary と完全等価（A5・SC#4 回帰防止・既存テスト全 GREEN）。

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-27T04:49:56Z
- **Completed:** 2026-06-27T04:58:48Z
- **Tasks:** 2
- **Files modified:** 4（src/model/orchestrator.py / src/model/artifact.py / src/model/predict.py / scripts/run_train_predict.py）

## Accomplishments

- orchestrator.train_and_predict が `theta: float | None = None` と `score_split: str = "test"` 引数を取り・theta=None で v1.0 binary と完全等価（A5 後方互換・SC#4 回帰防止）
- `_normalize_model_type` helper が `lightgbm_rr`→`lightgbm` / `catboost_rr`→`catboost` に正規化し・学習パスは base・model_version 採番は original を使用（codex HIGH#2）
- theta/model_type 双方向 guard（theta=float なら _rr 必須・_rr なら theta 必須・違反は ValueError）が冒頭に配置され・race-relative 補正済み確率が binary model_version で刻印される silent provenance hole を構造的ブロック（codex cycle-2 MEDIUM・T-11-13b）
- score_split="calib" が θ 選択経路を構造的に test 窓に触れさせない（§11.2 聖域の機械保証・docstring でなく API seam・codex HIGH#1）
- sales_start_entry_count を race_df_score から必須取得・race 内一意性 guard・groupby-size fallback なし（codex HIGH#6・D-08/D-09 singleton 一意性）
- race_relative.apply_race_relative_correction が LightGBM/CatBoost 両予測パスに挿入され・同一関数を呼ぶ（SC#3 bit-identical・D-01 binary 本体不変）
- 戻り値 dict に `race_relative_theta` と `score_split` provenance を追加（§19.1 再現性）
- artifact.save_native_artifact が metadata.json に `race_relative_theta` / `race_relative_alpha_search_xtol` (1e-9) / `race_relative_p_cal_clip_epsilon` (1e-6) を追加・α_r 自体は不保存（D-10 自己完結性）
- predict.MODEL_TYPE_TO_SHORT に `lightgbm_rr`→`lgbrr` / `catboost_rr`→`cbrr` を追加し・binary と race-relative が model_version で並列保存可能（SC#5 model_version-scoped idempotent swap 前提）
- scripts/run_train_predict.py が `race_relative_theta=result.get("race_relative_theta")` を save_native_artifact に渡すよう更新（codex MEDIUM・未更新だと None が書かれ SC#5 再現性が崩れる）

## Task Commits

各 task は原子的に commit された:

1. **Task 1: orchestrator.train_and_predict に theta + score_split + _normalize_model_type を追加（D-01/D-06・A5 後方互換・codex HIGH#1/#2/#6）** - `dedbd1a` (feat)
2. **Task 2: artifact.save_native_artifact metadata.json に theta provenance 追加 + predict.make_model_version short 識別子サポート + 呼出側更新（codex MEDIUM）** - `b5e540b` (feat)

_Note: TDD tasks でないため各 task は単一 commit（type: tdd でない・11-01/11-02 が RED/GREEN を担当）_

## Files Created/Modified

- `src/model/orchestrator.py` - theta/score_split 引数・_normalize_model_type helper・theta/model_type 双方向 guard・score_split による X_score/race_df_score 切替・sales_start_entry_count 必須取得（fallback なし）・race_relative 補正層挿入（両モデル共通）・race_relative_theta/score_split provenance
- `src/model/artifact.py` - save_native_artifact に race_relative_theta 引数・metadata.json に race_relative_theta / xtol / epsilon 追加（α_r は不保存・D-10）
- `src/model/predict.py` - MODEL_TYPE_TO_SHORT に lightgbm_rr/catboost_rr 追加・make_model_version docstring 拡張
- `scripts/run_train_predict.py` - save_native_artifact 呼出に race_relative_theta=result.get("race_relative_theta") を渡すよう更新

## Decisions Made

- **_normalize_model_type の配置:** module-level helper として train_and_predict の直前に配置。train_and_predict 本体で `base_model_type, original_model_type = _normalize_model_type(model_type)` を呼出し・以降の trainer/calib/予測パスは base_model_type を・model_version 採番と predict_p_fukusho model_type には original_model_type を使用。
- **双方向 guard の冒頭配置:** feature_df が未構築でも guard が発火するよう・train_and_predict 本体の最初の処理として配置。codex cycle-2 review で「冒頭配置なので feature_df なしでも guard が発火する」ことが要件と明記されていたため。
- **score_split="calib" の race_df_score 構築:** `calib_df.loc[X_calib.index, :]` から構築（splits["calib"] と整合）。test_df と同様の構造（race_key/race_date/sales_start_entry_count/race_start_datetime を含む label-joined frame）。
- **sales_start_entry_count 一意性 guard:** race 毎に np.unique で一意性を検証し・違反は RuntimeError。groupby().size() fallback は導入せず（dead code で D-08/D-09 を損なう・codex HIGH#6）。
- **race_relative 定数を metadata に数値リテラルで記述:** 循環 import を回避し・bit-identical 保証のため。race_relative.py の ALPHA_SEARCH_XTOL=1e-9 / P_CAL_CLIP_EPSILON=1e-6 と一致することを docstring で明記（変更時は両方を更新すること）。
- **α_r は metadata に保存しない:** D-10 自己完結性（α_r は θ + base logit + k から brentq で一意に決まる・完全再現可能）。
- **予測パスの X_score 切替:** LightGBM と CatBoost の両予測パスで X_test でなく X_score を使用。CatBoost の meta 列（race_start_datetime/race_key）は score_split に応じて race_df_score または test_df から取得。

## Deviations from Plan

None - plan executed exactly as written. PLAN の `<action>` 指示をそのまま実装した。以下・PLAN 指示との対応を明記:

- **codex HIGH#1（score_split）:** PLAN Task 1 action 【4】通り・X_score / race_df_score を構築し score_split で切替。L405 の race_df_test 構築後に配置。
- **codex HIGH#2（_normalize_model_type）:** PLAN Task 1 action 【3】通り・module-level helper として実装。trainer/calib/予測パスは base_model_type を・make_model_version は original_model_type を使用。
- **codex cycle-2 MEDIUM（双方向 guard）:** PLAN Task 1 action 【3b】通り・theta=float + binary model_type と model_type='_rr' + theta=None の両方で ValueError。冒頭配置で feature_df 無しでも発火。
- **codex HIGH#6（sales_start_entry_count）:** PLAN Task 1 action 【5】通り・race_df_score から必須取得・race 内一意性 guard・fallback なし。
- **codex MEDIUM（save_native_artifact 呼出）:** PLAN Task 2 action 通り・scripts/run_train_predict.py の呼出に race_relative_theta=result.get("race_relative_theta") を追加。

Auto-fixed Issues（Rule 1-3 適用）は**該当なし**。binary 本体（trainer.py / calibrator.py / data.py / evaluator.py / segment_eval.py / race_relative.py）は一切変更していない（D-01 聖域遵守）。

## Issues Encountered

None. verification スクリプト実行時に `CalibratedClassifierCV(cv='prefit')` が sklearn 1.9.0 で文字列削除されていることが判明したが（CLAUDE.md Decision「sklearn 1.9.0 で cv='prefit' 文字列削除のため FrozenEstimator 公式 prefit イディオムに適合」で既知）・本検証は artifact.roundtrip を直接の write_metadata_json に切り替えて完了（本番コードは fit_prefit_calibrator が正しい idiom を使うため影響なし）。

## User Setup Required

None - no external service configuration required.

## Threat Model Mitigations

PLAN の `<threat_model>` に基づく全 mitigation を実装済み:

| Threat | Severity | Disposition | 実装箇所 |
|--------|----------|-------------|----------|
| T-11-09（theta 選び直し・test 窓に θ が漏れる・Elevation of Privilege） | critical | mitigate | orchestrator は theta を再選択しない（受け取った値をそのまま適用）・score_split="calib" で θ 選択経路が構造的に test 窓に触れない（codex HIGH#1・§11.2 聖域の機械保証） |
| T-11-10（theta=None で v1.0 と非等価・SC#4 回帰・Tampering） | high | mitigate | theta=None の場合は補正層をスキップ（if theta is not None ブロック）・既存7テスト全 GREEN で回帰なしを保証（SC#4 bit-identical） |
| T-11-11（市場回帰・orchestrator が odds 参照・Information Disclosure） | high | mitigate | 補正層呼出は race_relative.apply_race_relative_correction のみ・orchestrator は odds/ninki を直接参照しない（race_relative.py は 11-01 で SAFE-01 AST 監査済み） |
| T-11-12（theta provenance 欠落・再現性崩壊・Repudiation） | high | mitigate | metadata.json に race_relative_theta / alpha_search_xtol (1e-9) / p_cal_clip_epsilon (1e-6) を必須記録・§19.1 再現性・scripts/run_train_predict.py が race_relative_theta を渡す（codex MEDIUM） |
| T-11-13b（theta=float + model_type が _rr でない silent provenance hole・Elevation of Privilege） | high | mitigate | train_and_predict 冒頭に theta/model_type 双方向 guard を実装（codex cycle-2 MEDIUM）・theta=float なら _rr 必須・_rr なら theta 必須・違反は ValueError |

## Known Stubs

該当なし。本 plan は統合層のみで・stub なし・race_relative.py は 11-02 で完全実装済み。

## Threat Flags

該当なし。本 plan は新たな trust boundary を導入しない・threat_model の T-11-09〜T-11-13b は全て acceptance_criteria で保証済み。

## Next Phase Readiness

- 11-04（Wave 3）は本 plan の orchestrator 拡張（theta + score_split）を消費し・run_phase11_evaluation.py で θ 選択経路を score_split="calib" で実行可能
- 11-05（Wave 4）は model_version で binary（-lgb-v1）と race-relative（-lgbrr-v1）を並列保存可能（SC#5 model_version-scoped idempotent swap）
- 全ての既存 Phase 4/5/6/9/10 の呼出は theta=None（既定）で破壊されない（A5 後方互換・SC#4 bit-identical 回帰防止・既存テスト全 GREEN）

---
*Phase: 11-race-relative-probability-model*
*Completed: 2026-06-27*

## Self-Check: PASSED

### 変更ファイルの存在確認

- FOUND: src/model/orchestrator.py（Task 1・theta + score_split + _normalize_model_type + 双方向 guard + 補正層 + provenance）
- FOUND: src/model/artifact.py（Task 2・race_relative_theta 引数 + metadata.json 拡張）
- FOUND: src/model/predict.py（Task 2・MODEL_TYPE_TO_SHORT lightgbm_rr/catboost_rr 追加）
- FOUND: scripts/run_train_predict.py（Task 2・save_native_artifact 呼出に race_relative_theta 追加）

### commit の存在確認

- FOUND: dedbd1a（Task 1・orchestrator theta + score_split + _normalize_model_type + 双方向 guard）
- FOUND: b5e540b（Task 2・artifact theta provenance + predict short 識別子 + run_train_predict 呼出更新）

### verification コマンドの実行結果

- `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/model/test_orchestrator.py tests/model/test_predict.py -x -k "not requires_db"` → **10 passed**（exit 0・A5 後方互換・SC#4 回帰防止）✓
- `uv run python -c "from src.model.predict import make_model_version; print(make_model_version('20260626-1a-opponentstrength-v1', 'lightgbm_rr', 1))"` → `20260626-1a-opponentstrength-v1-lgbrr-v1` ✓
- `uv run python -c "import inspect; from src.model.orchestrator import train_and_predict, _normalize_model_type; ..."` → theta/score_split 引数 + _normalize_model_type ✓
- `uv run python -c "import inspect, re; from src.model import orchestrator as o; ..."` → sales_start_entry_count 直参照あり + groupby-size fallback なし（codex HIGH#6）✓
- 双方向 guard 検証（feature_df 無しで theta=float+lightgbm / lightgbm_rr+theta=None / bad score_split 全て ValueError）✓
- metadata.json roundtrip（race_relative_theta / xtol / epsilon・α_r 不保存・byte-reproducible）✓
- binary 本体（trainer/calibrator/data/evaluator/segment_eval/race_relative.py）は files_modified に含まれない（D-01 聖域遵守）✓
