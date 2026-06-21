---
phase: 5
slug: ev-backtest
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-20
verified: 2026-06-21
---

# Phase 5 — Verification

> Phase 5 (EV & Backtest) 自動化部分の検証結果。実データ backtest（BT期間 2019-2025）は
> JODDS 取得進行中のため Manual-Only として明示的に分離（2段階実行計画・CONTEXT §domain 整合）。

---

## Automated Verification Results (2026-06-21)

### live-DB backtest スキーマ適用（Plan 05-06 Task 1）

`scripts/run_apply_schema.py` で `backtest.fukusho_backtest` テーブル + GRANT を適用済み。

```
$ uv run python scripts/run_apply_schema.py
applying step: create_schemas
applying step: create_roles
applying step: create_raw_views
applying step: prediction_table
applying step: backtest_table          ← BACKTEST_TABLE_DDL 適用
applying step: grant_reader            ← keiba_readonly に SELECT 付与
applying step: grant_etl               ← keiba_etl に 全権付与
applying step: revoke_raw_writes_public
applying step: revoke_raw_writes_view
schema applied successfully
```

**テーブル定義確認（\d backtest.fukusho_backtest）:**

- 列数: 33（provenance 10 + PK RACE_KEY 7 + umaban + 選択会計 7 + 的中/rank/EV 4 + odds provenance 3 + race_date 1）
- PK: `fukusho_backtest_pkey` btree (backtest_id, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum) — **8カラム**（backtest_id + RACE_KEY 7・review HIGH#1 と同一方針・silent 履歴破壊防止）
- CHECK 制約2個:
  - `backtest_model_type_domain`: `model_type IN ('lightgbm','catboost','bl3')`（D-04 BL-3 含む・T-05-13）
  - `backtest_strategy_domain`: `backtest_strategy_version = 'fukusho_ev_v1'`（§19.1 stamp）
- HIGH-1: `umaban` 列で馬単位永続化
- MEDIUM-04: `odds_missing_reason` 列（NULL 可能・normal 候補は NULL）

**GRANT 確認（\dp backtest.fukusho_backtest）:**

- `keiba_readonly=r`（SELECT のみ・reader ロール・§16.2 Streamlit 参照用）
- `keiba_etl=arwdD`（全権・ETL ロール・staging-swap idempotent load 用・T-05-14）

### 合成データフル行列 smoke（Plan 05-06 Task 1 / Plan 05-05 実装）

`scripts/run_backtest.py --synthetic` で BT-1..5 × {30min_before, 10min_before} × {lightgbm, catboost} + 5 BL-3 = **25 backtest** が完走。

```
$ uv run python scripts/run_backtest.py --synthetic
BT窓 BT-1: periods train=2019-06-01..2022-06-30 calib=2022-07-01..2022-12-31 test=2023-01-01..2023-12-31
backtest BT-1-30min_before-lightgbm: recovery=0.0000 P/L=0 ...
backtest BT-1-30min_before-catboost: recovery=0.0000 P/L=0 ...
backtest BT-1-10min_before-lightgbm: recovery=0.0000 P/L=0 ...
backtest BT-1-10min_before-catboost: recovery=0.0000 P/L=0 ...
BL-3 backtest BT-1-confirmed-bl3: recovery=1.7500 P/L=7200 selected=96
(... BT-2..BT-5 も同一構成 ...)
SUMMARY: 全 backtest 行=25 (主モデル 20 + BL-3 5)
reports generated: reports/05-backtest.md, reports/05-backtest.json
```

**reports 検証:**

- `reports/05-backtest.md`: 25 backtest が backtest_id 辞書順で一覧・「推奨:」突出行なし（BACK-04・grep `-c '推奨:'` == 0）・§11.2 odds policy 固定履行確認セクション含む・`backtest_strategy_version=fukusho_ev_v1` 明記
- `reports/05-backtest.json`: `comparison_table` 25 エントリ・`constants.FUKUSHO_EV_V1_STRATEGY='fukusho_ev_v1'`・全エントリが `REPORT_COLUMNS` キー保持・backtest_id 辞書順ソート

### フル pytest suite（KEIBA_SKIP_DB_TESTS 未設定・requires_db 含む）

```
$ uv run pytest -q
350 passed, 3 warnings in 343.94s
```

3 warnings は全て pre-existing LightGBM/sklearn 由来（`test_predict.py` の `X has feature names, but LogisticRegression was fitted without feature names`・Phase 4 でも確認済み・Phase 5 と無関係）。

**Phase 5 全 plan テスト内訳:**

- Plan 01: BT窓ヘルパ + Wave 0 RED stub（GREEN 化済み）= 15 + 44 tests
- Plan 02: EV/rank/purchase/metrics/bl3 純粋関数 = 23 tests
- Plan 03: odds_snapshot/refund_accounting = 30 tests
- Plan 04: split_3way periods + backtest_load（requires_db 4件 GREEN）= 36 tests
- Plan 05: run_backtest/report 合成データ E2E smoke = 14 tests
- Phase 4 回帰: model/db 系 = 既存 green 維持

---

## Per-Task Verification Map（最終状態）

| Task Area | Plan | Wave | Requirement | Test Type | Status |
|-----------|------|------|-------------|-----------|--------|
| EV_lower/EV_upper 計算 | 02 | 1 | EV-01 | unit | ✅ green |
| 推奨ランク S/A/B/C/D | 02 | 1 | EV-02 | unit | ✅ green |
| race_id-grouped split + BT窓 | 01 | 1 | BACK-01 | unit | ✅ green |
| 仮想購入ルール fukusho_ev_v1 | 02 | 1 | BACK-02 | unit | ✅ green |
| 返還会計 6シナリオ | 03 | 1 | BACK-03 | unit | ✅ green |
| odds 時点選択 backward | 03 | 1 | BACK-03 | unit | ✅ green |
| odds policy 固定・no_bet | 03 | 1 | BACK-04 | unit | ✅ green |
| staging-swap idempotent | 04 | 2 | BACK-03 | integration (requires_db) | ✅ green |
| 回収率/max drawdown | 02 | 2 | §11.6 | unit | ✅ green |
| BT窓再学習ループ | 04 | 2 | D-03 | integration | ✅ green |
| run_backtest フル行列 smoke | 05 | 4 | BACK-01..04 | E2E (synthetic) | ✅ green |
| report 全候補一括（winner 強調禁止） | 05 | 4 | BACK-04 | E2E | ✅ green |
| report REPORT_COLUMNS presence | 05 | 4 | LOW-05 | E2E | ✅ green |
| backtest.fukusho_backtest スキーマ適用 | 06 | 5 | BACK-03 | integration (live-DB) | ✅ green |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| **実データ backtest 実行（BT期間 2019-2025）** | BACK-01/04 | JODDS 取得進行中（2026-06-20 開始・2015年25レース日分のみ・分単位粒度・`public.n_jodds_tanpuku`）。実データ backtest は BT期間 2019-2025 の JODDS 取得完了後のみ実行可能。 | **JODDS 取得完了後**: `uv run python scripts/run_backtest.py`（`--synthetic` 外す・`--snapshot-id=20260620-1a-postreview-v2`）を実行。`MEDIUM-05` 相当の `_assert_jodds_coverage_horse_level` gate が candidate-horse usable-odds coverage < 0.90 で RuntimeError を raise するため・取得未完での誤実行を loud fail で防止（Plan 05-05 実装・CONTEXT §domain 整合）。生成された `reports/05-backtest.{md,json}` を実データ版として採用（合成データ版と差替）。 |
| 全25候補一括報告の目視（後知恵 winner 強調なし） | BACK-04 | 報告フォーマットの「推奨」記述欠如を目視 | `reports/05-backtest.md` に「推奨: BT-X」の記述が無いことを確認（主モデル確定は Phase 6 D-03/D-04 事前登録選定基準・Calibration 重視）。合成データ版で `grep -c '推奨:' reports/05-backtest.md` == 0 を実証済み。 |

### 実データ backtest の manual-only 分離（2段階実行計画）

Phase 5 は**2段階実行計画**を採用（CONTEXT §domain・VALIDATION Manual-Only と整合）:

1. **自動化部分（本 Plan 05-06 で完了）**: コード実装・単体テスト・合成データ E2E smoke・live-DB backtest スキーマ適用・reports 合成データ版生成・フル suite green（BACK-01..04 構造的ブロック全 GREEN）
2. **manual-only（JODDS 取得完了後）**: 実データ backtest 実行（BT期間 2019-2025・`scripts/run_backtest.py` で `--synthetic` を外す）・実データ版 reports 差替・目視確認

**誤実行防止ゲート**: `scripts/run_backtest.py` は `--synthetic` を外した実行で `_assert_jodds_coverage_horse_level`（horse-level usable-odds coverage < 0.90 で RuntimeError・race-level coverage < 0.95 も secondary check）を発火するため・JODDS 取得未完での誤実行は loud fail する（Plan 05-05 MEDIUM-B cycle-2 実装・T-05-17d mitigate）。

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（Plan 01 RED stub → Plan 02-05 で GREEN 化）
- [x] No watch-mode flags
- [x] Feedback latency < 30s（quick）/ ~6min（full）
- [x] `nyquist_compliant: true` set in frontmatter
- [x] live-DB backtest スキーマ適用確認（テーブル + GRANT）
- [x] 合成データフル行列 smoke GREEN・reports/05-backtest 生成
- [x] BACK-01..04 構造的ブロック GREEN（フル suite 350 passed + winner 報告禁止 + odds policy 固定）
- [x] 実データ backtest を manual-only として明示分離（本セクション Manual-Only に明記）

**Approval:** Phase 5 自動化部分 verified（2026-06-21）。実データ backtest は JODDS 取得完了後に manual-only で検証予定。
