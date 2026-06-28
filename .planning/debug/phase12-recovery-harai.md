---
slug: phase12-recovery-harai
status: resolved
trigger: "Phase 12 run_phase12_evaluation.py の _compute_recovery_rate が常に recovery=0.0 を返す (switch_recommendation の判断材料が無効化・Phase 12 の本当の結論 p_lower EV が出ない)"
created: 2026-06-28
updated: 2026-06-28
related_phase: "12"
related_plan: "12-05"
tags: [recovery-rate, harai, payout-key, gap-closure, switch-recommendation, p3-p5-decision]
---

# Debug: Phase 12 recovery_rate=0.0（HARAI 払戻列伝播不足 + payout キー誤り）

## 症状 (Symptoms)

- **再現**: live-DB で `uv run python scripts/run_phase12_evaluation.py --non-interactive` → reports/12-evaluation/12-evaluation.json の `recovery_rates` が `{baseline_v1_0_binary: 0.0, p_lower: 0.0}`。
- **影響**: switch_recommendation の判断材料（baseline_recovery_rate / p_lower_recovery_rate / recovery_rate_delta / ev_improved）が全て無効。Phase 12 の本当の結論（p_lower EV は本当にダメなのか）が出ない。

## 根因 (Root Cause・debug ログ実測で 2 層と判明)

debug ログ（`[P1-debug] select_bets / payout_total / stake_total`）で実測：
- baseline: `ranked=22793 → select_bets=2138 / payout_total=0.00 / stake_total=213800 → recovery=0.0`
- p_lower:  `ranked=22793 → select_bets=1    / payout_total=0.00 / stake_total=100    → recovery=0.0`

select_bets は空でない（baseline 2138件）。よって payout_total=0 が問題。

1. **P1（キー誤り・保持）**: `_compute_recovery_rate` が `determine_stake_payout` 戻り値から `payout_amount` を取得していたが、正しいキーは `payout`（refund_accounting.py L103/171-178）。run_backtest は L519 で `payout`→`payout_amount` alias を作る設計（metrics.py 等の `payout_amount` は DataFrame 列名として正しい）。_compute_recovery_rate は dict を直接参照するので `payout` が正しい。
2. **主原因（HARAI 払戻列伝播不足）**: `determine_stake_payout` → `_lookup_payfukusyo_pay`（refund_accounting.py L62-64）が `payfukusyoumaban1..5`/`payfukusyopay1..5` を探すが、eval コピーの pred_df にこれらの HARAI 払戻列が無い（`_attach_label_to_pred` の label_keep に含まれない）→ 全 slot `continue` → `payout=0`。run_backtest.py（L601-615・HIGH-C cycle-2）/ 09-05 stopgate（L859-923）は HARAI race-level merge idiom を持つが・run_phase12 は持たなかった。

## 修正 (Fix・scripts/run_phase12_evaluation.py のみ)

1. **`_fetch_harai_race_level`** 追加（09-05 stopgate L787-823 / run_backtest L1333-1359 を inline コピー）: `raw_everydb2.n_harai` から race-level 払戻 slot を SELECT（`year IN (...)` filter・test 窓のみ）・`make_race_key` で race_key 構築。
2. **`_attach_harai_to_pred`** 追加（新規・09-05 L908-923 の HARAI race-level merge）: pred_df に HARAI race-level merge（`validate='many_to_one'`・行数不変 assert）。**HARAI race_df の PK 系（year/jyocd/kaiji/nichiji/racenum）は pred_df の PREDICTION_COLUMNS と重複するため merge から除外**（衝突すると jyocd_x/jyocd_y に分裂し segment_eval の jyocd 軸が WARN skip になる）。
3. **main 統合**: JODDS fetch ブロック（readonly_cursor）に HARAI fetch を併設（n_harai は軽量・30s）→ `_ensure_entry_count` の後に baseline_pred/rr_pred へ `_attach_harai_to_pred` 適用。
4. **P1 修正**（`payout_amount → payout`・L1186）保持。

## 制約 (聖域・遵守)

- **SAFE-01**: HARAI 払戻は eval コピー（baseline_pred/rr_pred）のみ。FEATURE_COLUMNS / feature 構築経路に触れない。`rr_test_result["pred_df"]`（20-col PREDICTION_COLUMNS・load_predictions 用）に触れない。
- **§11.2 test 窓聖域**: HARAI 払戻は評価層（_compute_recovery_rate）での消費のみ。q_shrink 再計算経路では使わない。run_backtest も backtest で HARAI を消費（同等）。
- **§15.2 gate / Phase 12 WARN gate 不変**: recovery_rate は switch_recommendation（D-09）の入力で gate 対象でない。
- **byte-reproducible（§19.1）**: 2回実行で bit-identical。

## Evidence (live-DB)

- timestamp: 2026-06-28 13:24-13:36 — live-DB 実行 exit 0 (2回・jyocd 修正後)
- HARAI 払戻 JOIN: harai races=3456 (test 2023)
- **recovery_rate 正常化**: baseline `0.0 → 0.7314` / p_lower `0.0`（select_bets=1・1件ベースで参考程度・期待通り）
- WARNING 完全ゼロ（segment_eval 失敗・jyocd WARN skip 共に解消）
- jyocd 軸復活: baseline/rr 共に segment 0 → 10
- bit-identical: 2回実行で全 JSON/MD が sha256 完全一致
- gate 結果不変（98e150f 基準 vs HARAI 移植後）: §15.2 `block_triggered=False` / Phase12 `phase12_warn_triggered=True` / `falsification=feature_gap`（falsification.json bit-identical）/ `switch_recommendation=reject`（phase12_warn_triggered 優先・inputs.recovery_rate 値のみ正しくなった）
- unit test (KEIBA_SKIP_DB_TESTS=1): **731 passed, 48 skipped**（回帰なし）

## Resolution / 戦略判断材料（確定）

- baseline_recovery ≈ 0.73（Phase 5 既知の天井 0.65 付近・sensible）
- p_lower_recovery = 0.0（select_bets=1・1件ベース・実質0）= **「p_lower（現設計・q_level=0.90）は候補を選ぶ時点でほぼ全滅」という P3 の結論を数字で確定**
- recovery_rate_delta = -0.73（p_lower が baseline を大幅に下回る・ev_improved=False）
- → WARN gate FAIL（phase12_warn_triggered=True）+ select 数（p_lower=1）+ 誠実な回収率 を総合して、**P3（p_lower 条件付き/乗法への再設計）か P5（odds-free 限界受容・Phase 1-B）か**の戦略判断材料が確定。

## 目的の補足（ユーザー合意）

本修正の目的は「p_lower を救うため」でなく、「誠実な回収率を出して次の戦略判断（P3 vs P5）の材料を確定させるため」。HARAI 移植は P3 の結論を「数字で確定させる」だけで p_lower を救わない（候補選びの時点で既に全滅）。

memory: fix-must-verify-gate-result-livedb（live-DB で gate PASS/FAIL 不変を検証）・fukusho-recovery-070-structural-ceiling（複勝回収率~0.65天井）。
