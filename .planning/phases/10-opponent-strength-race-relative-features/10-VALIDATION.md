---
phase: 10
slug: opponent-strength-race-relative-features
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-26
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 内容は RESEARCH.md L662-700（Validation Architecture）と各 PLAN の `<verify>`/`<acceptance_criteria>` を機械転記した実値。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0（`requires_db` marker・`KEIBA_SKIP_DB_TESTS` 環境変数で live-DB 必須テストを切替） |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`・testpaths=["tests"]・addopts="-ra") |
| **Quick run command** | `uv run pytest tests/features/test_field_strength.py tests/features/test_race_relative.py tests/features/test_rolling.py tests/audit/test_audit_field_strength.py -x -q` |
| **Full suite command** | `uv run pytest` （`KEIBA_SKIP_DB_TESTS` unset で live-DB 必須テスト含む全テスト） |
| **Estimated runtime** | Quick ~15-30 秒 / Full ~3-5 分（live-DB 含む） |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/features/test_field_strength.py tests/features/test_race_relative.py tests/features/test_rolling.py tests/audit/test_audit_field_strength.py -x -q`（quick・合成データ・DB 不要）
- **After every plan wave:** Run `uv run pytest`（`KEIBA_SKIP_DB_TESTS=1` で live-DB 必須テストを skip した全テスト）
- **Before `/gsd-verify-work`:** Full suite must be green（`KEIBA_SKIP_DB_TESTS` unset・live-DB フルスイート + snapshot SHA256 + SC#5 非劣化 gate）
- **Max feedback latency:** 30 秒（quick）/ 5 分（full・live-DB 含む）

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | FEAT-02 / D-01 厳格版 as-of | T-10-01 (Tampering/lookahead) | 相手 rolling 能力が source race `available_at` **以前のみ**（strict `<`）・未来情報混入なし | unit + adversarial | `uv run pytest tests/features/test_field_strength.py -x -q` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 2 | FEAT-02 / D-06 第2段階 21 feature | T-10-06 (Cross-obs leak) | target 馬の過去走 profile が latest-K rolling で 21 feature 生成・obs_id group・sentinel/count ルール | unit | `uv run pytest tests/features/test_rolling.py -x -q -k "field_strength"` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 2 | FEAT-03 / D-07 rank 3軸・D-08 gap・D-10 同着・D-11/D-12 adjusted rank | T-10-10 (§11.2 聖域)・T-10-11/12 | race_id group・competition ranking（min rank "1224"）・target-only・欠損除外・0.25 canonical 事前登録・候補 {0.0,0.1,0.25,0.5} は train/calib 窓のみ | unit | `uv run pytest tests/features/test_race_relative.py -x -q` | ❌ W0 | ⬜ pending |
| 10-04-01 | 04 | 3 | FEAT-02/03 / builder 統合・registry | T-10-15/16 | builder Step 5c/5d/7/7b・feature_availability.yaml registry 27 feature・FEATURE_COLUMNS allowlist parity | unit | `uv run pytest tests/features/test_speed_figure_builder_integration.py tests/features/test_allowlist.py -x -q` | ✅ (既存・27 feature 拡張) | ⬜ pending |
| 10-05-01 | 05 | 4 | FEAT-02/03 / SC#3 byte-reproducible | T-10-17 (Reproducibility drift) | snapshot.py nullable Float64 扱い・FIXED_REPRODUCE_TS・決定論的 PyArrow 書込・SHA256（metadata 除外） | unit + live-DB | `uv run pytest tests/features/test_snapshot_repro.py -x -q` | ✅ (既存・27 feature 拡張) | ⬜ pending |
| 10-05-02 | 05 | 4 | FEAT-02/03 / SC#3 live-DB snapshot 生成 | T-10-18 (Silent data loss) | live-DB で snapshot 20260626-1a-opponentstrength-v1 生成・feature_count=106・2回 build SHA256 一致 | live-DB (checkpoint) | `shasum -a 256 snapshots/feature_matrix_20260626-1a-opponentstrength-v1.parquet`（2回一致） | ❌ W0 | ⬜ pending |
| 10-06-01 | 06 | 5 | FEAT-02/03 / FEATURE_COLUMNS 106 自動追従 | T-10-26 (snapshot_id 省略で stop gate 無意味化) | `_derive_feature_columns(snapshot_id='20260626-1a-opponentstrength-v1')==106` 且つ `==79`（baseline 20260620-1a-postreview-v2）回帰・make_X_y 完全一致 assert GREEN | unit | `uv run pytest tests/model/test_data.py -x -q -k "feature_columns or make_X_y"` | ✅ (既存・106 回帰拡張) | ⬜ pending |
| 10-06-02 | 06 | 5 | SC#5 非劣化 gate / D-16 事前登録 | T-10-23 (§11.2 聖域)・T-10-27 (SC#5 違反) | run_phase10_evaluation.py が D-16 許容幅（Brier ≤0.002 / LogLoss ≤0.005 / AUC ≤0.005）を事前登録定数化・両 snapshot 同一 trainer 設定で delta・binning 固定再利用 | live-DB + evaluation | `uv run python scripts/run_phase10_evaluation.py --phase10-snapshot-id 20260626-1a-opponentstrength-v1 --baseline-snapshot-id 20260620-1a-postreview-v2 --bt-split BT-1 --odds-snapshot-policy 30min_before --out-dir reports; echo "exit=$?"` | ❌ W0 | ⬜ pending |
| 10-06-03 | 06 | 5 | SC#5 live-DB gate 実行（checkpoint） | T-10-23 (§11.2 聖域) | live-DB で 3-way 比較実行・D-16 許容幅で PASS（3条件全成立）・聖域遵守（評価後すり替え禁止） | live-DB (checkpoint:human-verify) | （10-06-02 と同一コマンド・human が reports/10-evaluation の delta を確認） | ❌ W0 | ⬜ pending |
| 10-07-01 | 07 | 5 | SAFE-01 / SC#4 adversarial audit | T-10-28 (odds proxy)・T-10-29 (lookahead)・T-10-30 (false-pass) | AST Name/Attribute/SQL proxy 3層 0件・lookahead 注入で guard 有効性逆証明・5段階鋳型 false-pass 回避・FEATURE_COLUMNS forbidden prefix 0件 | unit + adversarial | `uv run pytest tests/audit/test_audit_field_strength.py tests/audit/test_audit_speed_figure.py -x -q` | ❌ W0 | ⬜ pending |
| 10-07-02 | 07 | 5 | SAFE-01 / Pitfall 2 性能検証 | T-10-31 (DoS・計算量爆発) | compute_field_strength_profile の vectorized 実装が縮小版 14000 行で 5 秒以内・cProfile で Python ループ hot spot 無し | unit (perf) | `uv run pytest tests/features/test_field_strength.py -x -q -k "performance or hot_spot"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Phase 10 は feature 構築・評価 gate 層。テスト基盤（pytest 9.1.0・`KEIBA_SKIP_DB_TESTS`・`tests/` ディレクトリ）は Phase 6-9.1 で確立済み。Wave 0 で新規/拡張すべきファイル:

- [ ] `tests/features/test_field_strength.py` — FEAT-02 第1段階 profile・PIT strict `<`・発走馬特定（kakuteijyuni>0）・profile 8値・top-k クランプ・**Pitfall 2 性能検証（縮小版 14000 行 ≤5 秒・cProfile hot spot）**
- [ ] `tests/features/test_race_relative.py` — FEAT-03 rank 3軸・gap top/3rd・competition ranking・adjusted rank・欠損馬除外・**候補別一時列の非残存**（feature_matrix.columns に coef_* が存在しない）unit test
- [ ] `tests/audit/test_audit_field_strength.py` — AST odds/ninki proxy 排除・SQL proxy（REVIEW H5）・FEATURE_COLUMNS allowlist parity・false-pass 回避・lookahead 注入（`_pit_cutoff_prefilter` monkeypatch `<=` 版）adversarial
- [ ] `tests/features/test_rolling.py` 拡張 — `rolling_field_strength_*` 21 feature unit test（median/best2/trend/sentinel ルール・D-09.1-01/03 と対称）
- [ ] `tests/features/test_speed_figure_builder_integration.py` 拡張 — hardcode feature list 27 新 feature 追加（feature_count 79 → 106）
- [ ] `tests/audit/test_audit_speed_figure.py` 拡張 — expected_features hardcode list に Phase 10 の 27 feature 追加（SAFE-01 検査対象拡張）
- [ ] `tests/features/test_snapshot_repro.py` 拡張 — snapshot 20260626-1a-opponentstrength-v1 の byte-reproducibility（FEAT-03 nullable Float64・SHA256 一致）
- [ ] `tests/model/test_data.py` 拡張 — `_derive_feature_columns(snapshot_id='20260626-1a-opponentstrength-v1')==106` 且つ `==79`（baseline）回帰・make_X_y snapshot_id 明示伝播 GREEN
- [ ] `scripts/run_phase10_evaluation.py` 新規 — SC#5 非劣化 gate（baseline vs Phase 10 snapshot 3-way 比較・`run_speed_figure_stopgate.py` 鋳型・D-16 許容幅事前登録）

*テスト基盤自体は既存（pytest/pyproject.toml）。Wave 0 は上記ファイルの新規/拡張のみ。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| live-DB snapshot 生成（feature_count=106・SHA256 2回一致） | FEAT-02/03 / SC#3 | 本番規模データ（48万行・3万4千レース）の Parquet 書込は CI の合成データでは再現不能 | PLAN 05 Task 2: `KEIBA_SKIP_DB_TESTS` unset・statement_timeout 設定→`run_feature_build.py` で snapshot 生成→2回 build で SHA256 一致を確認 |
| live-DB SC#5 非劣化 gate（D-16 許容幅） | SC#5 / D-16 | Phase 6 D-07 水準との比較は live-DB snapshot で v1.0 LightGBM を再学習する必要あり・合成データでは無意味 | PLAN 06 Task 3: `run_phase10_evaluation.py` 実行→reports/10-evaluation の Brier/LogLoss/AUC delta が D-16 許容幅（≤0.002/≤0.005/≥-0.005）内か確認・聖域遵守（超過時は許容幅変更ではなく feature 見直し） |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（上記 Wave 0 Requirements に列挙）
- [x] No watch-mode flags（全て `-x -q` single-shot）
- [x] Feedback latency < 30s（quick）/ < 5min（full live-DB）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-26（revision: checker B-1 対応・実値埋込）
