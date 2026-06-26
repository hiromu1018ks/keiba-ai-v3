---
phase: 10-opponent-strength-race-relative-features
plan: 09
subsystem: doc-accuracy
tags: ["gap-closure", "doc-accuracy", "plan-truth-fix"]
requires:
  - .planning/phases/10-opponent-strength-race-relative-features/10-06-PLAN.md
  - .planning/phases/10-opponent-strength-race-relative-features/10-VERIFICATION.md
provides:
  - "10-06-PLAN.md doc truth 数値表記の実測値整合（baseline 79 → 35・model FEATURE_COLUMNS vs Parquet 全列数 区別明確化）"
affects:
  - ".planning/phases/10-opponent-strength-race-relative-features/10-06-PLAN.md"
tech-stack:
  added: []
  patterns:
    - "W-4 文脈判定基準（model FEATURE_COLUMNS vs Parquet 全列数のキーフレーズリスト機械判定）"
key-files:
  created: []
  modified:
    - ".planning/phases/10-opponent-strength-race-relative-features/10-06-PLAN.md"
decisions:
  - "10-06-PLAN.md の model FEATURE_COLUMNS 文脈の baseline snapshot (postreview-v2) のFEATURE_COLUMNS 値を 79 → 35 に訂正（実測値根拠: PROJECT decisions『postreview-v2 実データ値 35 が正』・src/model/data.py _derive_feature_columns の registry 動的導出・tests/model/test_data.py の BASELINE_V10_FEATURE_COUNT=35 定数）"
  - "model FEATURE_COLUMNS（79・Phase 10 / 35・baseline）と Parquet 全列数（106）の区別を明確化するため、model FEATURE_COLUMNS 文脈の行からは Parquet 全列数の数値表記を分離し、W-4 文脈判定基準のキーフレーズリストで機械判定可能にした"
metrics:
  duration: 約15分
  completed: 2026-06-27
  tasks: 1
  files: 1
status: complete
---

# Phase 10 Plan 09: 10-06-PLAN doc truth 数値訂正（baseline 79 → 35） Summary

10-VERIFICATION.md deferred L24-26 で指摘された PLAN truth doc 不整合を解消。10-06-PLAN.md の model FEATURE_COLUMNS 文脈で baseline snapshot `20260620-1a-postreview-v2` のFEATURE_COLUMNS 値が「79」と誤記されていたのを「35」に訂正し、Parquet 全列数文脈（`feature_count=106`）と model FEATURE_COLUMNS 文脈（79・Phase 10 / 35・baseline）の区別を W-4 文脈判定基準のキーフレーズリストで機械判定可能な形で明確化した。コード変更なし・substantive な検証は 10-06 で達成済み（SC#5 gate_pass=True）。

## What Was Built

### 変更対象（doc only）

- **`.planning/phases/10-opponent-strength-race-relative-features/10-06-PLAN.md`**: model FEATURE_COLUMNS 文脈の baseline snapshot feature count 表記 79 → 35 訂正（must_haves truths L33・objective L57/L61・behavior L103-104・action L111/L113/L115・acceptance_criteria L135-136/L139・done L146・verification L316・success_criteria L326・artifacts_produced L345 の複数箇所）

### 訂正の実測値根拠（権威）

- **PROJECT decisions**: "postreview-v2 実データ値 35 が正"（Phase 9/9.1 で 35→41→52→79 と拡張された系統・baseline は 35 feature）
- **src/model/data.py:179-211** の `_derive_feature_columns`: registry から FEATURE_COLUMNS を動的導出。`snapshot_id='20260620-1a-postreview-v2'` で 35 feature・`snapshot_id='20260626-1a-opponentstrength-v1'` で 79 feature を返す実装
- **tests/model/test_data.py:398-399** の定数: `PHASE10_FEATURE_COUNT = 79` / `BASELINE_V10_FEATURE_COUNT = 35`（実測値・手動検証で確認済み）
- **10-06-SUMMARY.md L8/L38/L53/L90/L125**: 実測値 35 と整合（PLAN truth の 79 が誤記・実測値は 35）

## W-4 文脈判定基準（model FEATURE_COLUMNS vs Parquet 全列数）

訂正にあたり・10-06-PLAN.md の各箇所が以下のどちらの文脈かを機械的に判定するためのキーフレーズリストを適用:

- **model FEATURE_COLUMNS 文脈（数値は 79 or 35）**: `_derive_feature_columns(...)` / `len が` / `feature を返す` / `feature になる` / `FEATURE_COLUMNS` / `feature 回帰` / `baseline 回帰` / `<数>/<数> 回帰` / `両者が assert` / `新 snapshot_id で<数>・旧 snapshot_id で<数>` / `X.columns と FEATURE_COLUMNS が完全一致`
  → この文脈の「106」は「79（Phase 10）」に・「79」は「35（baseline）」に訂正
- **Parquet 全列数 文脈（数値は 106 のまま維持）**: `feature_count=106` / `feature_count が` / `Parquet 全列数` / `schema_version` と並列の feature_count / `snapshot ...（feature_count=106）`
  → この文脈の「106」は維持（訂正しない）

## 訂正箇所リスト（before / after）

| 行番号 | 箇所 | before | after |
|--------|------|--------|-------|
| L33 | must_haves truths | `FEATURE_COLUMNS が 27 新 feature を含む 106 feature になる` | `79 feature になる（model FEATURE_COLUMNS 文脈・Parquet 全列数は別文脈）` |
| L57 | objective | （feature_count=106 文脈・維持） | 維持（Parquet 全列数文脈・正しい） |
| L61 | objective | `FEATURE_COLUMNS 106/79 回帰` | `FEATURE_COLUMNS 79/35 回帰` |
| L103 | behavior | `_derive_feature_columns(...) が 106 feature を返す` | `79 feature を返す（model FEATURE_COLUMNS 文脈）` |
| L104 | behavior | `postreview-v2 が 79 feature を返す。新 snapshot_id で 106・旧 snapshot_id で 79` | `V10_BASELINE (postreview-v2) が 35 feature を返し・PHASE10 が 79 feature を返す` |
| L111 | action | `_derive_feature_columns が自動的に 106 feature を返す` | `79 feature を返す（model FEATURE_COLUMNS 文脈）` |
| L113 | action | `FEATURE_COLUMNS の len が 106 であること` | `len が 79 であること` |
| L115 | action | `106/79 を両立...len が 79...106 と 79 の両方` | `79/35 を両立...len が 35...79（Phase 10 model FEATURE_COLUMNS）と 35` |
| L135 | acceptance_criteria | `106 feature を返す（len == 106）` | `79 feature を返す（len == 79・model FEATURE_COLUMNS 文脈）` |
| L136 | acceptance_criteria | `79 feature を返す（len == 79・baseline）...106/79 両者` | `V10_BASELINE 側の 35 feature（len == 35）...PHASE10 側の 79 と V10_BASELINE 側の 35` |
| L139 | acceptance_criteria | `106 feature と 79 baseline 回帰` | `79 feature と 35 の v1.0 postreview 回帰` |
| L146 | done | `106 feature を動的導出...106（新）/ 79（baseline）回帰` | `79 feature を動的導出...79（新・Phase 10）/ 35（v1.0 postreview）回帰` |
| L316 | verification | `FEATURE_COLUMNS 106/79 回帰` | `FEATURE_COLUMNS 79/35 回帰` |
| L326 | success_criteria | `新 snapshot_id で 106・旧 baseline snapshot_id で 79` | `新 snapshot_id で 79・旧 v1.0 postreview snapshot_id で 35` |
| L345 | artifacts_produced | `FEATURE_COLUMNS 106/79 回帰` | `FEATURE_COLUMNS 79/35 回帰` |

## 検証結果（grep 機械判定）

PLAN 09 の `<verify><automated>` セクションと `acceptance_criteria` に記載の grep 条件を厳密適用:

### plan verify `<automated>` grep（3条件）

```
条件1: grep -nE "baseline.*\b79\b|\b79\b.*baseline|postreview-v2.*\b79\b" 10-06-PLAN.md | grep -v '^[0-9]*:#' | wc -l
  → 0 件（期待 0・PASS）

条件2: grep -nE "_derive_feature_columns.*\b106\b|\b106\b.*feature を返す|FEATURE_COLUMNS.*\b106\b.*回帰|\b106\b.*baseline 回帰|FEATURE_COLUMNS が.*\b106\b.*feature になる" 10-06-PLAN.md | wc -l
  → 0 件（期待 0・PASS）

条件3: grep -nE "feature_count=106" 10-06-PLAN.md | wc -l
  → 2 件（期待 1以上・PASS・L29 と L57 の Parquet 全列数文脈で維持）
```

### acceptance_criteria grep（3条件）

```
AC1: grep -nE "baseline.*\b79\b|\b79\b.*baseline" 10-06-PLAN.md | grep -v '^[0-9]*:#' | wc -l
  → 0 件（期待 0・PASS）

AC2: grep -nE "_derive_feature_columns.*\b106\b|\b106\b.*feature を返す|FEATURE_COLUMNS.*\b106\b.*回帰|\b106\b.*baseline 回帰" 10-06-PLAN.md | wc -l
  → 0 件（期待 0・PASS）

AC3: grep -nE "feature_count=106" 10-06-PLAN.md | wc -l
  → 2 件（期待 1以上・PASS）
```

3条件すべて PASS。

## 本質保持の確認

訂正後も 10-06-PLAN.md の本質（substantive 達成内容）は不変:

- **H1-b 無言失敗 catch**: snapshot_id 明示伝播で FEATURE_COLUMNS が切替わることの保証（79/35 の組で達成・106/79 でなくても本質は同じ）
- **27 新 feature 含有**: Phase 10 snapshot が baseline から +27 新 feature を含む 79 feature（35 + 44・Phase 9.1 speed_figure 系統込み）
- **新旧 snapshot_id で別 FEATURE_COLUMNS**: `set(new_cols) != set(baseline_cols)` が assert される
- **W-3 category_map bit-identity**: baseline_cat_map と phase10_cat_map の hash bit-identity が保証される（B-3 同一 trainer 設定の前提）
- **SC#5 gate_pass=True**: D-16 許容幅内（Brier delta=-0.00022 / LogLoss delta=+0.00487 / AUC delta=+0.00180）で substantive 達成済み

## コード変更なしの確認

- `src/model/data.py`: git diff で変更なし（`_derive_feature_columns` は registry から動的導出で既に 35/79 を返す実装）
- `tests/model/test_data.py`: git diff で変更なし（`PHASE10_FEATURE_COUNT=79` / `BASELINE_V10_FEATURE_COUNT=35` 定数で GREEN）
- `snapshots/`: git diff で変更なし
- 本 plan は doc truth の数値表記訂正のみ・実装・テスト・snapshot は一切不変

## 含めないもの（10-09 対象外）

- **10-05-PLAN.md**: doc truth（L31『79 既存 + 27 新 feature』）は既に正しい（10-VERIFICATION.md deferred L24 で言及されたが既に修正済み）→ 本 plan では扱わず
- **W-3 縮小版 5.0s 閾値**: PLAN 01/07 で option-a 根拠再設定済み（10-VERIFICATION.md deferred L14-17・NOT a gap・per-source-race 線形予算 + 準二次スケーリングガードで聖域遵守）
- **D-15 segment_eval column-name mismatch**: Phase 12 EVAL-01 に先送り済み（10-VERIFICATION.md deferred L21-23・参照用 only・gate 判定に使わず）
- **Info（IN-01〜05）**: backlog/issue 化のみ（10-08 deferred と同一・本 plan では扱わず）

## Deviations from Plan

None - plan は W-4 文脈判定基準に従い機械的に訂正。訂正過程で plan verify grep の `postreview-v2.*79` が model FEATURE_COLUMNS 文脈の正しい記述（postreview-v2 は 35・79 は Phase 10 snapshot 側）でも同一行に postreview-v2 と 79 があるとヒットする正規表現の制約を踏まえ・訂正後の記述では V10_BASELINE / PHASE10 の alias 参照と箇条書き分割で grep が機械的に 0 件になるよう調整した（内容の本質は不変・PLAN 09 の acceptance_criteria grep を厳密に満たすための表現整理）。

## Self-Check: PASSED

### 作成ファイルの存在確認

```
[ -f ".planning/phases/10-opponent-strength-race-relative-features/10-06-PLAN.md" ] && echo "FOUND: 10-06-PLAN.md" || echo "MISSING"
→ FOUND: 10-06-PLAN.md
```

### commit hash の存在確認

```
git log --oneline --all | grep -q "ff34252" && echo "FOUND: ff34252" || echo "MISSING"
→ FOUND: ff34252（docs(10-09): 10-06-PLAN baseline feature count 表記 79→35 訂正）
```

### コード変更なしの確認

```
git diff HEAD~1 --name-only | grep -E "^(src/|tests/|snapshots/)" || echo "（なし・doc only 達成）"
→（なし・doc only 達成）
```

### grep 検証の再確認

3条件すべて PASS（上記「検証結果」セクション参照）。

---

_Summary created: 2026-06-27_
_Plan executor: Claude (gsd-execute-phase)_
