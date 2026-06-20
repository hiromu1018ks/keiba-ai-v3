---
phase: 4
slug: model-prediction
status: approved
nyquist_compliant: true
wave_0_complete: true
final_gate_run_with_skip_unset: true
created: 2026-06-20
approved: 2026-06-20
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 各成功基準（SC#1-#4）とリーク面について、unit / adversarial / smoke / integration の階層化検証を規定する。
> 出典: `04-RESEARCH.md` "## Validation Architecture"（実コード・実データ裏取り済み）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（`tests/` 配下・Phase 1-3 既存 + `tests/model/` 新設） |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]`（testpaths=["tests"]・markers `requires_db`） |
| **Quick run command** | `uv run pytest tests/model/ -x -q` |
| **Full suite command** | `uv run pytest`（KEIBA_SKIP_DB_TESTS unset で実行・review HIGH#10） |
| **Observed runtime** | tests/model/ quick = ~26s / full suite (KEIBA_SKIP_DB_TESTS unset) = **315–321s**（262 passed・38 requires_db 全実行） |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/model/ -x -q`（model 配下の quick subset）
- **After every plan wave:** `uv run pytest`（既存 + model/ 新設の全件）
- **Final gate (PLAN 06):** `unset KEIBA_SKIP_DB_TESTS && uv run pytest` で critical テスト（`requires_db` マーク 38 件）の skipped count == 0 を確認（review HIGH#10: green-by-skip 防止）
- **Feedback latency:** 実行時間は参考指標（review MEDIUM: critical テストを縮小/skip して短縮することは禁止）

---

## Per-Task Verification Map

> 実行証拠（PLAN 06 で実測）を各 test 行に付記: 実行コマンド・終了コード・該当する場合は checksum / artifact SHA256 / 行数。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status | 実行証拠 (PLAN 06) |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|--------|--------------------|
| 04-02-T1 | 02 | 0 | MODL-01 / SC#1 | T-04-04 | stamped Parquet **のみ**から学習（live DB 参照しない） | unit | `uv run pytest tests/model/test_data.py::test_load_from_parquet_only -x` | ✅ GREEN | exit 0 (`uv run pytest tests/model/ -q` 全 37 passed の一環) |
| 04-02-T1 | 02 | 0 | MODL-01 / SC#1 | T-04-04 | raw ID 原列（kisyucode 等4列）はモデル入力から除外 | unit | `uv run pytest tests/model/test_data.py::test_raw_ids_excluded -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-02-T1 | 02 | 0 | MODL-01 / SC#1 | T-04-05 | feature allowlist 検査（odds/banned feature 非混入） | unit | `uv run pytest tests/model/test_data.py::test_no_banned_features -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-03-T1 | 03 | 0 | MODL-03 / SC#3 | T-04-01 | LightGBM native categorical（非負 int32 code・NaN→-1 禁止） | unit | `uv run pytest tests/model/test_trainer.py::test_lightgbm_nonneg_codes -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-03-T1 | 03 | 0 | MODL-03 / SC#3 | T-04-01 | CatBoost `has_time=True`・Pool は race_start_datetime sort | unit | `uv run pytest tests/model/test_trainer.py::test_catboost_has_time -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-03-T1 | 03 | 0 | MODL-03 / SC#3 | T-04-01 | target encoding 非混入（rare category が自身の label に一致せず平均に縮む） | adversarial | `uv run pytest tests/model/test_trainer.py::test_no_target_encoding_leak -x` | ✅ GREEN | exit 0 / **SC#3 対抗的構造診断** (低基数 RARE_X + 高基数 _code train-only/test-unseen + 意図的リーク制御で DEMONSTRABLY fail を確認) / review HIGH#3: live-data 証明と称さず対抗的構造診断と正確に呼ぶ / 実行時間 12.40s |
| 04-02-T1 | 02 | 0 | SC#4 | T-04-02 | strict-later disjoint（`max(train.race_date) < min(calib.race_date)`） | unit | `uv run pytest tests/model/test_calibrator.py::test_strict_later_disjoint -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-05-T1 | 05 | 0 | SC#4 | T-04-29 | reproduce bit-identical（固定 seed → 再学習・再予測で同一予測） | smoke | `uv run pytest tests/model/test_orchestrator.py::test_reproduce_bit_identical -x` | ✅ GREEN | exit 0 / **SC#4 構造的ブロック** (両モデル seed=42 + num_threads=1/thread_count=1 + FIXED_REPRODUCE_TS で np.array_equal) / 実行時間 2.38s / ※ 04-05 で calibrator.py → orchestrator.py に移動済 (review HIGH#12) |
| 04-02-T1 | 02 | 0 | BACK-01（前置）/ SC#1 | T-04-02 | race_id 分離 disjoint（3way で同一 race_id 跨り禁止） | unit | `uv run pytest tests/model/test_data.py::test_race_id_disjoint_3way -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-03-T2 | 03 | 0 | MODL-02 / SC#2 | — | BL-1..5 厳密定義・市場データ源（ninki / fukuoddslow/high） | unit | `uv run pytest tests/model/test_baseline.py -x` | ✅ GREEN | exit 0 / 6 test (BL-1..5 + 市場データ源) / ※ BL-2/BL-3 市場データ test split で NaN（市場データ取得範囲のデータ可用性 gap・Phase 6 で再評価） |
| 04-04-T1 | 04 | 0 | MODL-01 | T-04-05 | prediction provenance 列（model_version/feature_snapshot_id/as_of_datetime） | unit | `uv run pytest tests/model/test_predict.py::test_provenance_columns -x` | ✅ GREEN | exit 0 (37 passed の一環) |
| 04-04-T2 | 04 | 0 | D-05 | — | staging-swap idempotent（2回実行で同一 checksum） | integration | `uv run pytest tests/model/test_prediction_load.py -x` | ✅ GREEN | exit 0 / 実データ E2E で idempotent checksum verify PASS: lightgbm=72713b7a54872bba30f354f8e04adf3f / catboost=268687d5a8fbc5b36b9cf990574f4e59 |
| 04-03-T1 | 03 | 0 | D-04 / SC#3 | T-04-03 | early stopping eval set が calib/test と分離（未来情報非漏洩） | unit | `uv run pytest tests/model/test_trainer.py::test_eval_set_disjoint_from_calib_test -x` | ✅ GREEN | exit 0 (37 passed の一環) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Wave 0（実装着手前）で用意すべき test stub・fixture・依存インストール。RED 状態で計画完了→実装で GREEN 化する TDD→RED-first は planner が wave 構成で決定。

- [x] `tests/model/__init__.py` — package marker
- [x] `tests/model/test_data.py` — SC#1（Parquet のみ / raw ID 除外 / allowlist / race_id disjoint 3way）
- [x] `tests/model/test_trainer.py` — SC#3（leak diagnostic / has_time / nonneg codes / eval set 分離）
- [x] `tests/model/test_calibrator.py` — SC#4（strict-later disjoint / isotonic<1000 sigmoid 切替）
- [x] `tests/model/test_orchestrator.py` — SC#4 reproduce bit-identical + 行整列 + Cycle 2 NEW HIGH-1/residual #13（review HIGH#12 で calibrator.py から移動）
- [x] `tests/model/test_baseline.py` — BL-1..5 厳密定義・市場データ源
- [x] `tests/model/test_predict.py` — provenance 列・model_version 採番
- [x] `tests/model/test_prediction_load.py` — staging-swap idempotent（2回実行同一 checksum）
- [x] Framework install: `uv add lightgbm==4.6.0 catboost==1.2.10`（CLAUDE.md 指示版 pin・RESEARCH D-11）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| （該当なし） | — | — | — |

*All phase behaviors have automated verification.*（Phase 4 は全成功基準が unit/adversarial/smoke/integration で自動検証可能。live-DB を使う snapshot rebuild 等の「許可済み人手確認」は checkpoint として別途設定されるが、これは verification 手順であり manual-only 検証項目ではない。）

---

## Final Gate Execution Evidence (PLAN 06 / 2026-06-20)

### SC#3 leak diagnostic — review HIGH#3（対抗的構造診断と正確に呼ぶ）

- コマンド: `uv run pytest tests/model/test_trainer.py::test_no_target_encoding_leak -x -v`
- 終了コード: 0 / 1 passed in 12.40s
- 構造: 低基数希少カテゴリ RARE_X（両モデル予測が mean ≈0.21 に縮み `< 0.5`）+ 高基数 `_code` 列 train-only/test-unseen ID（global mean に縮む）+ 意図的 target encoding 制御注入（予測 > 0.9 で false-pass でないことを証明）
- 注記: live-data 証明と称さず・**対抗的構造診断（合成データ）** と正確に呼ぶ・Phase 8 adversarial audit が live-data での別途検証を担う

### SC#4 reproduce smoke — review HIGH#7（固定 thread/as_of_datetime）

- 単体テスト: `uv run pytest tests/model/test_orchestrator.py::test_reproduce_bit_identical -x -v` → exit 0 / 1 passed in 2.38s
- 実データ pipeline: `uv run python scripts/run_train_predict.py --model-type both --check-reproduce`
  - 終了コード: 0
  - 出力: `SC#4 reproduce smoke PASS (lightgbm)` / `SC#4 reproduce smoke PASS (catboost)` / `SC#4 reproduce smoke: 全モデル PASS`
  - 固定条件: seed=42 + num_threads=1 (lightgbm) / thread_count=1 (catboost) + FIXED_REPRODUCE_TS = datetime(2026,6,20,tzinfo=UTC)

### 両モデル E2E pipeline（実データ・DB 書込あり）

- コマンド: `uv run python scripts/run_train_predict.py --model-type both --check-reproduce`
- 終了コード: 0
- feature_df: 552,935 行（label-joined・81 列）
- LightGBM: model_version=`20260620-1a-postreview-v2-lgb-v1` / calib_method=isotonic / pred_rows=22,213 / checksum=`72713b7a54872bba30f354f8e04adf3f`
- CatBoost:  model_version=`20260620-1a-postreview-v2-cb-v1` / calib_method=isotonic / pred_rows=22,213 / checksum=`268687d5a8fbc5b36b9cf990574f4e59`
- prediction idempotent verify: 両モデル PASS（2 回目実行で checksum 一致）

### prediction.fukusho_prediction テーブル（両モデル永続化）

- 確認 SQL: `SELECT model_type, model_version, count(*) FROM prediction.fukusho_prediction GROUP BY model_type, model_version`
- 結果: catboost / `20260620-1a-postreview-v2-cb-v1` / 22,213 行 + lightgbm / `20260620-1a-postreview-v2-lgb-v1` / 22,213 行
- ※ model_version スコープ swap（review HIGH#1）で他 model_type/version の行を破壊せず・両モデル共存を確認

### artifact SHA256（base+calibrator 分離・review HIGH#5）

```
ce769f0ccbb4f02d0e5970efa92cb00ba44b984515683385e75ddad388d8426a  models/20260620-1a-postreview-v2-lgb-v1/lgb_model.txt
c28ef8dcdb4495b22493c25cb3603cb16d93c2cd9568e25fdc050c4f7b330a41  models/20260620-1a-postreview-v2-lgb-v1/calibrator.joblib
076374a391c1766bbf59038951181a77def51ecfcc5f254b009ebcc24a8e6d4e  models/20260620-1a-postreview-v2-lgb-v1/metadata.json
0897735af3b9737be6dc42e9c3e0b217f412a1cf95936fe6a9a2aad69a1d187e  models/20260620-1a-postreview-v2-cb-v1/cb_model.cbm
f7cde8289982bdf44e9385bc31d0e6704d5fe2116759dd0921132169ea1d8b1d  models/20260620-1a-postreview-v2-cb-v1/calibrator.joblib
4140ad5ea541e0ef637d877068c07b20c5e51e0ccb0fe3b5f31f34612169fcab  models/20260620-1a-postreview-v2-cb-v1/metadata.json
```

### reports/04-eval.{md,json} SHA256

```
98d6b17db61ad887a91bb913a27f8b64c66e6f822e2997a157bcbd49a035d120  reports/04-eval.md
8b668dfae287b5d3b810fb845efdde935417cb803eb5fce1f4844abe1a657244  reports/04-eval.json
```

### 最終ゲート（KEIBA_SKIP_DB_TESTS unset）— review HIGH#10: green-by-skip 防止

- コマンド: `unset KEIBA_SKIP_DB_TESTS && uv run pytest`
- 結果: **262 passed, 3 warnings in 315.53s**（2 回目実行で 321.45s）・0 failed / **0 skipped**
- `uv run pytest -rs` で `^SKIPPED` 行 0 件を確認
- `requires_db` マーク付きテスト（38 件）が全て実行された（KEIBA_SKIP_DB_TESTS unset で skip なし）
- テスト収集数: 262

### SC#2 比較表 + 主モデル vs baselines 具体指標比較（review HIGH#8）

(a) **比較表生成済み**: reports/04-eval.md / reports/04-eval.json に LightGBM + CatBoost + BL-1..5 の比較表が生成されている。

(b) **主モデル vs baselines 具体指標比較**:

| 指標 | LightGBM | CatBoost | BL-1 | BL-2 | BL-3 | BL-4 | BL-5 |
|------|----------|----------|------|------|------|------|------|
| brier | **0.152216** | 0.154529 | 0.169530 | NaN | NaN | 0.168700 | 0.167097 |
| logloss | **0.474883** | 0.482434 | 0.521015 | NaN | NaN | 0.518246 | 0.513048 |
| auc | **0.732295** | 0.718001 | 0.573953 | NaN | NaN | 0.601986 | 0.619879 |
| calibration_max_dev | 0.230769 | 0.257893 | **0.001426** | NaN | NaN | 0.044928 | 0.343709 |
| sum_p_mean | 3.041678 | 3.067278 | 2.958365 | NaN | NaN | 3.246690 | 3.107941 |

- **Brier / LogLoss / AUC**: 主モデル（LightGBM/CatBoost）が BL-1/BL-4/BL-5 を上回る（LightGBM が最良）。
- **Calibration（D-04 事前登録の主要選定基準）**: 主モデル `calibration_max_dev` 0.230769 / 0.257893 に対し・BL-1=0.001426（constant 予測）・BL-4=0.044928（未キャリブレーション）が低位。**主モデルは calibration_max_dev で BL-1/BL-4 より劣る**。
- **結論（review HIGH#8 正直注記）**: Brier/LogLoss/AUC（順序付け性能）では AI モデルが baselines を上回るが・**D-04 事前登録の主要基準である Calibration（calibration_max_dev）では BL-1/BL-4 に劣る**。事前登録基準（Calibration 重視）の観点からは **「AI 付加価値 未証明（部分証明）」** と正直に注記する。Phase 6 ゲートで最終選定基準を適用して最終判定を行う。BL-4/BL-5 は主モデルと同一 calib slice でキャリブレーションされていない点（calibrate_bl4_bl5=False）にも注意・Phase 6 で公平比較を再評価する。

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency 記録（critical テスト縮小/skip なし・実測 315–321s）— review MEDIUM: 実行時間は参考指標
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` set in frontmatter
- [x] `final_gate_run_with_skip_unset: true` set in frontmatter — review HIGH#10

**Approval:** approved (2026-06-20 / PLAN 06 完了時点)
