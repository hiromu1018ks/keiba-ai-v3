---
phase: 11
slug: race-relative-probability-model
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-27
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `11-RESEARCH.md` §Validation Architecture（HIGH confidence・実証検証済み）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（`pyproject.toml` pin・既存・marker `requires_db`） |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]`（testpaths=["tests"]・addopts="-ra"） |
| **Quick run command** | `uv run pytest tests/unit/test_race_relative.py -x` |
| **Full suite command** | `uv run pytest tests/`（`KEIBA_SKIP_DB_TESTS` unset で live-DB フルスイート） |
| **Estimated runtime** | ~60 秒（unit）/ ~数分（live-DB フルスイート） |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_race_relative.py -x`
- **After every plan wave:** Run `uv run pytest tests/unit/ tests/audit/ -x`
- **Before `/gsd-verify-work`:** `uv run pytest tests/`（`KEIBA_SKIP_DB_TESTS` unset・live-DB フルスイート） must be green
- **Max feedback latency:** ~60 秒（unit）/ 数分（live-DB）

---

## Per-Requirement Verification Map

> planner が task ID（`11-NN-MM`）を割り当てた後、各 task 行へ展開。ここでは requirement→test の契約を固定（SC#1-5・D-09/D-10 聖域を全て自動検証で覆盖）。

| Req / SC | Behavior | Test Type | Automated Command | File Exists | Status |
|----------|----------|-----------|-------------------|-------------|--------|
| MODEL-01 | α_r 二分探索が sum(p)=k を厳密達成（\|sum−k\| < 1e-9・brentq xtol=1e-9） | unit | `uv run pytest tests/unit/test_race_relative.py::test_solve_alpha_sum_p_equals_k -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | α_r 二分探索が単調増加 f(α) で唯一解（IVT） | unit | `uv run pytest tests/unit/test_race_relative.py::test_alpha_monotonic_unique_solution -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | θ→∞ で α → logit(k/n) に収束（平坦化の理論値） | unit | `uv run pytest tests/unit/test_race_relative.py::test_theta_inf_limit -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | θ→0+ で brentq 失敗（尖鋭化・発散検出） | unit | `uv run pytest tests/unit/test_race_relative.py::test_theta_zero_divergence -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | clip ε=1e-6 で isotonic 0/1 端点生成時に sum(p)=k 精度 <1e-12 | unit | `uv run pytest tests/unit/test_race_relative.py::test_clip_epsilon_isotonic_endpoints -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | apply_race_relative_correction が race 毎に独立動作（他 race 不参照） | unit | `uv run pytest tests/unit/test_race_relative.py::test_race_independence -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | base logit s_i が両モデルで bit-identical（logit(proba) 経路・atol=1e-6） | unit | `uv run pytest tests/unit/test_race_relative.py::test_base_logit_bit_identical -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | sum(p)=k 不変性が完全パイプラインで成立（補正後追加 calib なし） | unit | `uv run pytest tests/unit/test_race_relative.py::test_pipeline_sum_p_invariant -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | overprediction penalty が segment_eval binning と bit-identical | unit | `uv run pytest tests/unit/test_race_relative.py::test_overprediction_penalty_binning_parity -x` | ❌ W0 | ⬜ pending |
| MODEL-01 | k 決定が sales_start_entry_count ベース・同着不反映 | unit | `uv run pytest tests/unit/test_race_relative.py::test_k_determination_no_deadheat -x` | ❌ W0 | ⬜ pending |
| SAFE-01/D-09 | binary logit 欠損で RuntimeError（neutral 補完不採用・silent fallback 禁止） | unit | `uv run pytest tests/unit/test_race_relative.py::test_logit_missing_fail_loud -x` | ❌ W0 | ⬜ pending |
| D-10 | α_r 自己完結性: outcome 入れ替えで α_r/p 不変 | adversarial audit | `uv run pytest tests/audit/test_audit_race_relative.py::test_alpha_self_contained_outcome_swap -x` | ❌ W0 | ⬜ pending |
| D-10 | α_r 自己完結性: 他 race logit 混入検出 | adversarial audit | `uv run pytest tests/audit/test_audit_race_relative.py::test_alpha_cross_race_leak_detected -x` | ❌ W0 | ⬜ pending |
| SC#3 | 両モデル（LightGBM/CatBoost）で race-relative p が bit-identical | integration | `uv run pytest tests/unit/test_race_relative.py::test_both_models_bit_identical -x` | ❌ W0 | ⬜ pending |
| SC#4 | SAFE-01 proxy 排除: 補正層モジュールの AST odds/ninki 0 件 | adversarial audit | `uv run pytest tests/audit/test_audit_race_relative.py::test_no_odds_ninki_proxy -x` | ❌ W0 | ⬜ pending |
| SC#5 | model_version-scoped swap で idempotent（2 回実行で checksum bit-identical） | integration (live-DB) | `KEIBA_SKIP_DB_TESTS= uv run pytest tests/ -k "idempotent" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_race_relative.py` — stubs for MODEL-01（α_r 二分探索・clip・sum(p)=k・bit-identical・overprediction penalty・k 決定・fail-loud・パイプライン不変性）
- [ ] `tests/audit/test_audit_race_relative.py` — stubs for D-10（α_r 自己完結性・outcome swap・cross-race leak）・SAFE-01 SC#4（補正層 AST odds/ninki proxy 0 件・Phase 8 D-06 5段階鋳型踏襲）
- [ ] `src/model/race_relative.py` — 新規モジュール（pure 関数・テストが依存する公開 API の stub）
- [ ] `scripts/run_phase11_evaluation.py` — v1.0 vs race-relative 比較・SC#2 gate・θ 選択経路記録（実行は後続 wave・Wave 0 は存在保証のみで可）

*Framework install: 不要 — pytest 9.1.0 既存 pin。新規依存なし（scipy.optimize.brentq は SciPy >=1.17.1 既存 pin）。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| θ 候補集合の事前登録値が Plan に固定されていること（§11.2 聖域・test 窓選び直し禁止） | MODEL-01/D-03 | 設計意図の事前登録は文書契約（コード検証対象でない） | Plan の `<specifics>` / must_haves に候補集合（推奨 `{0.5,0.75,1.0,1.25,1.5}`・θ=1 baseline 含む）と足切り→選択→tie-break ルールが固定値で記載されているか目視 |
| SC#2 gate（D-04 非劣化マージン + D-05 改善 gate 3条件）が test 窓で一回だけ評価されること | MODEL-01/D-04/D-05 | 後知恵すり替え禁止は実行プロセス契約 | `reports/11-*` に test 窓評価が一回のみ・calib slice で θ 選択した経路が記録されているか確認 |

*上記以外の全振る舞い（α_r 健全性・自己完結性・bit-identical・proxy 排除・idempotent swap・fail-loud・sum(p)=k）は自動検証で覆盖。*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references（`test_race_relative.py`・`test_audit_race_relative.py`・`race_relative.py`）
- [ ] No watch-mode flags
- [ ] Feedback latency < 数分（live-DB フルスイート）
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
