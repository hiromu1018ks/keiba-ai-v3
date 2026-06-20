---
phase: 4
slug: model-prediction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-20
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 各成功基準（SC#1-#4）とリーク面について、unit / adversarial / smoke / integration の階層化検証を規定する。
> 出典: `04-RESEARCH.md` "## Validation Architecture"（実コード・実データ裏取り済み）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（既存・`tests/` 配下 24 ファイル・Phase 1-3 で 216+ tests GREEN） |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]`（testpaths=["tests"]・markers `requires_db`） |
| **Quick run command** | `uv run pytest tests/model/ -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60–120 秒（model/ 新設 + 既存 24 ファイル・LightGBM/CatBoost 学習は small sample で短縮可） |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/model/ -x -q`（model 配下の quick subset）
- **After every plan wave:** `uv run pytest`（既存 24 ファイル + model/ 新設の全件）
- **Before `/gsd-verify-work`:** Full suite must be green — SC#3 leak diagnostic / SC#4 reproduce smoke / race_id disjoint が GREEN であること
- **Max feedback latency:** 120 秒

---

## Per-Task Verification Map

> Task ID は planner が PLAN.md を出力後に確定・埋められる。下表は SC/要件単位の検証契約（RESEARCH.md "### Phase Requirements → Test Map" に基づく）。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (PLAN 後割当) | — | 0 | MODL-01 / SC#1 | T-04-04 | stamped Parquet **のみ**から学習（live DB 参照しない） | unit | `uv run pytest tests/model/test_data.py::test_load_from_parquet_only -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-01 / SC#1 | T-04-04 | raw ID 原列（kisyucode 等4列）はモデル入力から除外 | unit | `uv run pytest tests/model/test_data.py::test_raw_ids_excluded -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-01 / SC#1 | T-04-05 | feature allowlist 検査（odds/banned feature 非混入） | unit | `uv run pytest tests/model/test_data.py::test_no_banned_features -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-03 / SC#3 | T-04-01 | LightGBM native categorical（非負 int32 code・NaN→-1 禁止） | unit | `uv run pytest tests/model/test_trainer.py::test_lightgbm_nonneg_codes -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-03 / SC#3 | T-04-01 | CatBoost `has_time=True`・Pool は race_start_datetime sort | unit | `uv run pytest tests/model/test_trainer.py::test_catboost_has_time -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-03 / SC#3 | T-04-01 | target encoding 非混入（rare category が自身の label に一致せず平均に縮む） | adversarial | `uv run pytest tests/model/test_trainer.py::test_no_target_encoding_leak -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | SC#4 | T-04-02 | strict-later disjoint（`max(train.race_date) < min(calib.race_date)`） | unit | `uv run pytest tests/model/test_calibrator.py::test_strict_later_disjoint -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | SC#4 | — | reproduce bit-identical（固定 seed → 再学習・再予測で同一予測） | smoke | `uv run pytest tests/model/test_calibrator.py::test_reproduce_bit_identical -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | BACK-01（前置）/ SC#1 | T-04-02 | race_id 分離 disjoint（3way で同一 race_id 跨り禁止） | unit | `uv run pytest tests/model/test_data.py::test_race_id_disjoint_3way -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-02 / SC#2 | — | BL-1..5 厳密定義・市場データ源（ninki / fukuoddslow/high） | unit | `uv run pytest tests/model/test_baseline.py -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | MODL-01 | T-04-05 | prediction provenance 列（model_version/feature_snapshot_id/as_of_datetime） | unit | `uv run pytest tests/model/test_predict.py::test_provenance_columns -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | D-05 | — | staging-swap idempotent（2回実行で同一 checksum） | integration | `uv run pytest tests/model/test_prediction_load.py -x` | ❌ W0 | ⬜ pending |
| (PLAN 後割当) | — | 0 | D-04 / SC#3 | T-04-03 | early stopping eval set が calib/test と分離（未来情報非漏洩） | unit | `uv run pytest tests/model/test_trainer.py::test_eval_set_disjoint_from_calib_test -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Wave 0（実装着手前）で用意すべき test stub・fixture・依存インストール。RED 状態で計画完了→実装で GREEN 化する TDD→RED-first は planner が wave 構成で決定。

- [ ] `tests/model/__init__.py` — package marker
- [ ] `tests/model/test_data.py` — SC#1（Parquet のみ / raw ID 除外 / allowlist / race_id disjoint 3way）
- [ ] `tests/model/test_trainer.py` — SC#3（leak diagnostic / has_time / nonneg codes / eval set 分離）
- [ ] `tests/model/test_calibrator.py` — SC#4（strict-later disjoint / reproduce smoke / isotonic<1000 sigmoid 切替）
- [ ] `tests/model/test_baseline.py` — BL-1..5 厳密定義・市場データ源
- [ ] `tests/model/test_predict.py` — provenance 列・model_version 採番
- [ ] `tests/model/test_prediction_load.py` — staging-swap idempotent（2回実行同一 checksum）
- [ ] Framework install: `uv add lightgbm==4.6.0 catboost==1.2.10`（CLAUDE.md 指示版 pin・RESEARCH D-11）

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| （該当なし） | — | — | — |

*All phase behaviors have automated verification.*（Phase 4 は全成功基準が unit/adversarial/smoke/integration で自動検証可能。live-DB を使う snapshot rebuild 等の「許可済み人手確認」は checkpoint として別途設定されるが、これは verification 手順であり manual-only 検証項目ではない。）

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
