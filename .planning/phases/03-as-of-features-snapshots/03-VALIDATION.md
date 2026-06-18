---
phase: 3
slug: as-of-features-snapshots
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-18
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `03-RESEARCH.md` § Validation Architecture（workflow.nyquist_validation = true のため必須）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（Phase 1-2 実績・`uv run pytest`） |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`（既存・Phase 1 D-01） |
| **Quick run command** | `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q` |
| **Full suite command** | `uv run pytest -q`（DB 含む・Phase 1 実測 76 tests in 124s） |
| **Estimated runtime** | quick ~15-30s / full ~140-180s（Phase 3 で約 90-100 tests 予定） |

---

## Sampling Rate

- **After every task commit:** Run `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/features/ -q`（合成 DataFrame・高速）
- **After every plan wave:** Run `uv run pytest tests/features/ -q`（DB 接続含む・実データで feature 構築確認）
- **Before `/gsd-verify-work`:** Full suite must be green（`uv run pytest -q`）
- **Max feedback latency:** ~30s（quick）/ ~180s（full）

---

## Per-Task Verification Map

> 詳細な task ↔ test 対応は planner が PLAN.md の `<acceptance_criteria>` で確定する。本表は RESEARCH.md § Validation Architecture の要件→テスト対応を正とする。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-XX-01 | TBD | 1 | SC#1 / FEAT-01 | T-03-01 | 各 feature 行が `as_of_datetime`/`feature_cutoff_datetime`/`feature_snapshot_id`/`feature_availability` を持ち、`merge_asof(direction='backward')` で未来情報を排除する | unit + property | `uv run pytest tests/features/test_pit_cutoff.py -q` | ❌ W0 | ⬜ pending |
| 03-XX-02 | TBD | 1 | SC#2 / FEAT-02 | T-03-02 | feature matrix に禁止 timing（`post_race_only`/`odds_snapshot_available`/`body_weight_announced`/`race_day_morning`/`same_day_aggregate`）の feature が **0件**（fail-loud BLOCK） | unit (BLOCK) | `uv run pytest tests/features/test_allowlist.py::test_no_banned_timing_features -q` | ❌ W0 | ⬜ pending |
| 03-XX-03 | TBD | 2 | SC#3 / §12.4 | T-03-03 | Parquet snapshot が §12.4 8項目 metadata を持ち、再読込で同一 SHA256（byte-reproducibility） | unit + property | `uv run pytest tests/features/test_snapshot_repro.py::test_byte_reproducible_by_hash -q` | ❌ W0 | ⬜ pending |
| 03-XX-04 | TBD | 2 | SC#4 / §14.3-§14.4 | T-03-04 | frozen category map が train 窓（2016H2-2023）でのみ fit され、val/test の未知 ID が `__UNSEEN__` に map される | unit | `uv run pytest tests/features/test_category_map_consumer.py::test_unseen_maps_to_sentinel -q` | ❌ W0 | ⬜ pending |
| (副) D-05 | TBD | 1 | SC#2 副 | T-03-05 | 推定脚質が当日 `kyakusitukubun` を使わず、過去走 `jyuni3c`/`jyuni4c` のみから導出される | unit | `uv run pytest tests/features/test_running_style.py -q` | ❌ W0 | ⬜ pending |
| (副) D-03 | TBD | 1 | FEAT-01 副 | T-03-06 | lookback=5 で5走未満は `__MISSING__` sentinel（silent fill 禁止・Phase 1 D-13 整合） | unit | `uv run pytest tests/features/test_rolling.py::test_under_5_starts_uses_missing_sentinel -q` | ❌ W0 | ⬜ pending |
| (副) D-06 | TBD | 1 | SC#1 副 | T-03-07 | `feature_cutoff_datetime == race_date - 1 day` の厳格適用（同日別レース混入防止） | unit | `uv run pytest tests/features/test_pit_cutoff.py::test_cutoff_excludes_same_day_races -q` | ❌ W0 | ⬜ pending |
| (副) D-09 | TBD | 2 | FEAT-01 副 | T-03-08 | feature matrix が全期間1枚で train/val/test 境界に依存しない（同一 feature 値） | property | `uv run pytest tests/features/test_builder.py::test_split_independence -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/features/__init__.py` — package 化
- [ ] `tests/features/conftest.py` — 共通 fixture（合成 `n_uma_race` / `n_race` DataFrame・`feature_availability.yaml` 読込・readonly cursor mock）
- [ ] `tests/features/test_allowlist.py` — SC#2 fail-loud 検査（禁止 timing feature が1件でも FAIL）
- [ ] `tests/features/test_pit_cutoff.py` — SC#1 + D-06 cutoff enforcement（同日レース排除）
- [ ] `tests/features/test_rolling.py` — D-03（lookback=5）/ D-04（平均+最新値+SD の3軸）+ `__MISSING__`
- [ ] `tests/features/test_running_style.py` — D-05 推定脚質アルゴリズム（過去走 `jyuni3c`/`jyuni4c` のみ・当日不使用）
- [ ] `tests/features/test_snapshot_repro.py` — SC#3 byte-reproducibility（PyArrow deterministic write + SHA256）
- [ ] `tests/features/test_category_map_consumer.py` — SC#4 train-only fit + `__UNSEEN__` sentinel
- [ ] `tests/features/test_builder.py` — D-09 全期間1枚 + 分割非依存

*Framework install: 不要（pytest 9.1.0 は Phase 1 で導入済み）*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 代表デモ境界（train 2016H2-2023 / val 2024）の実際の row count が研究値（25939 / 3456 races）と整合 | D-09 | 実 DB クエリだが builder 実行後に確認 | builder 実行後 `snapshots/` manifest の train/val period bounds と row count を目視照合 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references（`tests/features/` 全 stub）
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s（quick）
- [ ] `nyquist_compliant: true` set in frontmatter（planner が task ↔ test 対応確定後）

**Approval:** pending
