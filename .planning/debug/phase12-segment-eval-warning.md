---
slug: phase12-segment-eval-warning
status: resolved
trigger: "Phase 12 評価スクリプト run_phase12_evaluation.py で falsification 後に segment_eval 失敗の WARNING が2行 (baseline/rr) 出る (D-15 参考記録・gate は影響しないが放置好ましくない)"
created: 2026-06-28
updated: 2026-06-28
related_phase: "12"
related_plan: "12-05"
tags: [segment-eval, d15-reference, label-column-mismatch, y-true-col, byte-reproducible, gate-invariant]
---

# Debug: Phase 12 segment_eval WARNING (y_true_col 不整合)

## 症状 (Symptoms)

- **再現**: live-DB で `uv run python scripts/run_phase12_evaluation.py --non-interactive`
- **失敗**: falsification 処理の直後に同じ WARNING が2行 (baseline と rr):
  `[WARNING] run_phase12_evaluation: segment_eval 失敗 (参考記録・gate 継続): evaluate_all_segments: y_true_col='fukusho_hit' が df に存在しない`
- **影響度**: D-15「参考記録」(診断のおまけ) で gate 合否判定対象でない。try/except で包まれているため処理は完走するが、警告のまま放置は好ましくない。

## 根因 (Root Cause)

`_safe_evaluate_all_segments` (run_phase12_evaluation.py L930-939 旧) が `evaluate_all_segments(pred_df)` を**デフォルト引数**で呼んでいた。`evaluate_all_segments` のデフォルトは `y_true_col="fukusho_hit"` (segment_eval.py L298/L333) だが、Phase 12 の pred_df (eval コピー) の正解列は `_attach_label_to_pred` (L279 `label_keep=["race_key","umaban","fukusho_hit_validated"]`) が JOIN した **`fukusho_hit_validated`** であり `fukusho_hit` は存在しない。→ `ValueError` → except で `logger.warning` (baseline/rr の2行)。

Phase 11 (run_phase11_evaluation.py L981-985) も同一 idiom だが、本件は Phase 12 のみ対象 (Phase 11 はスコープ外)。

## Current Focus

- **hypothesis**: segment_eval.py の既定契約 (Phase 6 保護) は触らず、呼出側で `y_true_col='fukusho_hit_validated'` と pred_df 列構成に合わせた axes を明示渡せば例外が消え D-15 参考記録データが生成される。
- **test**: live-DB 2回実行で WARNING 消滅 + reports bit-identical + gate 結果不変 + unit test 回帰なし。
- **next_action**: (完了) 修正適用 → live-DB 検証 → atomic commit。

## 修正 (Fix)

`scripts/run_phase12_evaluation.py` のみ変更 (segment_eval.py は Phase 6 契約保護のため不変):

1. `_PHASE12_SEGMENT_AXES` 定数追加 — pred_df (eval コピー) の実列構成 (PREDICTION_COLUMNS + label/odds JOIN) に合わせた5軸:
   - `year`/`month` → `race_date` (PREDICTION_COLUMNS 補助メタ)
   - `jyocd` → `jyocd` (PK 系)
   - `entry_count` → `entry_count` (`_ensure_entry_count` で確保)
   - `odds_band` → `fuku_odds_lower` (SEGMENT_AXES 既定は `fukuoddslower`・pred_df は `fuku_odds_lower`・odds JOIN)
   - `ninki` は除外 (pred_df に ninki 列無し・WARN skip 回避・Pitfall 6)
2. `_safe_evaluate_all_segments` で `y_true_col="fukusho_hit_validated"` + `axes=_PHASE12_SEGMENT_AXES` を明示渡す。

## 制約 (聖域・遵守)

- **§15.2 gate 不変 (D-06)**: `check_acceptance_gate` 一切触らない。D-15 は参考記録。
- **segment_eval.py 既定契約不変 (Phase 6 保護)**: `y_true_col='fukusho_hit'` / `SEGMENT_AXES` デフォルトは変更せず、呼出側で明示渡す (他フェーズ回帰回避)。
- **byte-reproducible (§19.1)**: 2回実行で reports/12-evaluation/*.json が bit-identical。
- **SAFE-01 / §11.2**: odds は評価層のみ・FEATURE_COLUMNS 非混入・test 窓聖域。`load_predictions` は元の20列 pred_df を維持 (odds 結合は評価用コピーのみ) — 本修正は odds 経路に触れない。

## Evidence

- timestamp: 2026-06-28 07:20-07:31 — live-DB 実行 exit 0 (2回)
- 1回目/2回目ログ: `segment_eval 失敗` WARNING **0行** (消滅確認)
- segment 欄実データ化: baseline/rr 共に `{year:1, month:12, jyocd:10, entry_count:12, odds_band:4}` segments (旧 `{"error": "..."}`)
- bit-identical: 1回目 vs 2回目で全 JSON/MD が sha256 完全一致
- gate 結果不変 (修正前後で同一): §15.2 `block_triggered=False` / Phase12 `phase12_warn_triggered=True` / `switch_recommendation=reject` / `q_shrink=0.3328315161410432` / `recovery_rates` 同一 / falsification.json bit-identical (`feature_gap`)
- falsification.json / falsification-spec.json / q_shrink.json / switch-recommendation.json: 修正前と bit-identical (segment 非依存)
- unit test (KEIBA_SKIP_DB_TESTS=1): **731 passed, 48 skipped** (回帰なし)

## Resolution

WARNING 2行消滅・segment_eval が例外なく D-15 参考記録データ (5軸) を生成。gate 結果は完全不変 (聖域遵守)。byte-reproducible 維持。

差分 (`git diff --stat`): `scripts/run_phase12_evaluation.py` (29行) + `reports/12-evaluation/12-evaluation.json` (segment 欄の実データ化・gate フィールド不変)。`12-evaluation.md` は不変 (`_format_evaluation_markdown` は segment 欄を表示しない)。

memory: `fix-must-verify-gate-result-livedb` — live-DB で gate PASS/FAIL 不変を検証 (unit test では検出不可)。
