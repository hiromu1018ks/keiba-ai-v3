# ステップ2: is_primary 切替 → A1（speedfigure-v1・binary・v1.1.0）+ 切替後 BT

- **Spike**: 001 (`.planning/spikes/001-ablation-recovery/`)
- **Quick Task**: `260628-t2s`（`.planning/quick/260628-t2s-switch-is-primary-to-a1-speedfigure-v1-l/`）
- **実行日**: 2026-06-28
- **A1**: snapshot `20260625-1a-speedfigure-v1`・LightGBM binary・label v1.1.0（commit 2cdbac1・newcomer '12' 誤除外修正後・eligible 42214）

## 0. 聖域（core value・全て遵守）

- **D-10**: is_primary 切替は人間承認の別アクション（手順2 で AskUserQuestion により承認取得・set_primary_model 明示呼出）。
- **odds-free (SAFE-01)**: speed figure は走破タイム由来・オッズ不使用。
- **PIT-correct**: feature_cutoff_datetime = race_date-1day・過去走のみ。
- **byte-reproducible**: seed=42・thread=1・FIXED_REPRODUCE_TS=2026-06-20 00:00 UTC。
- **H1-b**: `snapshot_id=A1` で FEATURE_COLUMNS 選択（speed figure 6・v1.0 デフォルト誤使用防止）。
- **§11.2**: test 窓 outcome を学習/閾値選択に使わない（run_ablation は no_write_db）。
- **Phase 11/12 凍結維持**（reopen せず・guard C-12-02-1）。

## 1. 手順1: A1 予測生成 + prediction 保存 + idempotent 検証

`run_train_predict.py` は `data.py` SNAPSHOT_PATH 固定（postreview-v2）で A1 を扱えないため（`_assert_snapshot_id_matches_data_module` L174-193 が sys.exit(1)）、`scripts/save_primary_prediction.py`（run_ablation chain 流用・Phase 4 標準 split）を新設。

- **chain**: `load_feature_matrix(A1)` + `load_labels`(v1.1.0) + `build_training_frame` → `train_and_predict(model_type="lightgbm", feature_snapshot_id=A1, snapshot_id=A1, version_n=1, seed=42, as_of_datetime=FIXED_REPRODUCE_TS, split_periods=None, category_map=None, label_version="v1.1.0", odds_snapshot_policy="30min_before", backtest_strategy_version="fukusho_ev_v1")` → `load_predictions` ×2
- **model_version**: `20260625-1a-speedfigure-v1-lgb-v1`（`make_model_version` 形式・コマンド指定と一致）
- **pred_rows**: 18737（Phase 4 標準 test 2024下期・label v1.1.0・speed fig 算出可能馬）
- **calib_method**: isotonic
- **idempotent verify PASS**: checksum `926aa1ddd82325c5b01d40abdfe62b58`（2回実行で bit-identical・D-05 staging-swap）✓ **受入基準2**
- **is_primary=False で保存**（predict 既定・D-09・手順2 で True 化）

## 2. 手順2: is_primary 切替（D-10 人間承認）

`scripts/switch_primary_model.py`（`--dry-run` で内容確認後・AskUserQuestion で D-10 承認取得 → `--confirm` で実行）。同一トランザクションで:

1. **Step1** `set_primary_model(primary_model_type="lightgbm", primary_model_version="20260625-1a-speedfigure-v1-lgb-v1", feature_snapshot_id="20260625-1a-speedfigure-v1", as_of_datetime=FIXED_REPRODUCE_TS)` → A1 スコープ reset→True（post-condition REVIEW HIGH#7 pass・当該スコープで is_primary=true が1 model_type のみ）
2. **Step2** `UPDATE prediction.fukusho_prediction SET is_primary=false WHERE model_version='20260620-1a-postreview-v2-lgb-v1'` → 既存デプロイ主モデル（別スコープ・set_primary_model では触れない）を降ろし

### DB before/after

| model_version | feature_snapshot_id | is_primary (BEFORE) | is_primary (AFTER) | n |
|---|---|---|---|---|
| 20260620-1a-postreview-v2-cb-v1 | postreview-v2 | False | False | 22213 |
| 20260620-1a-postreview-v2-lgb-v1 | postreview-v2 | **True** | False | 22213 |
| **20260625-1a-speedfigure-v1-lgb-v1** | **speedfigure-v1** | False | **True** | **18737** |
| 20260626-1a-opponentstrength-v1-lgbrr-v1 | opponentstrength-v1 | False | False | 22793 |

**受入基準1 PASS**: A1（20260625-1a-speedfigure-v1-lgb-v1）のみ is_primary=True（他は全て False）✓

> 注: postreview-v2 は as_of=2026-06-20 20:13:33（実行時刻・label v1.0.0）。A1 は as_of=FIXED_REPRODUCE_TS=2026-06-20 00:00 UTC（byte-reproducible・label v1.1.0）。set_primary_model は feature_snapshot_id+as_of スコープ限定のため、別スコープの postreview-v2 は Step1 で reset されず Step2 で明示 False 化（受入基準1 厳密満たす・設計判断3）。

## 3. 手順3: 切替後 BT-1..5 検証（Spike 001 一致・byte-reproducible）

`scripts/run_ablation.py --mode snap-swap --snapshot-id 20260625-1a-speedfigure-v1 --bt-window BT-X`（no_write_db・is_primary 切替と完全独立）。

| BT窓 | Spike 001 期待 | 切替後 実測 | n_selected | hit | P/L | _full_candidate |
|---|---|---|---|---|---|---|
| BT-1 (test 2023) | 1.0459 | **1.045859** | 4359 | 572 | +19990 | 42214 |
| BT-2 (test 2024) | 1.178118 | **1.178118** | 4378 | 563 | +77980 | 41745 |
| BT-3 (test 2025) | 1.091590 | **1.091590** | 4031 | 609 | +36920 | 42403 |
| BT-4 (rolling 2024) | 1.173491 | **1.173491** | 4308 | 540 | +74740 | 41745 |
| BT-5 (rolling 2024) | 1.192085 | **1.192085** | 4498 | 572 | +86400 | 41745 |

**受入基準3 PASS**: 5窓全て Spike 001 と完全一致（byte-reproducible・is_primary 切替の副作用無し）✓
- 切替後 JSON: `reports/12-evaluation/ablation-a1-bt{1..5}-postswitch.json`

## 4. 手順3b: Phase 4 標準窓（test 2024下期）A1 vs postreview-v2 比較

ユーザー指示追加（PLAN 手順3b）。本番デプロイ運用と同じ test 窓スコープ（Phase 4 標準・postreview-v2 現行と同一構造）で A1 と postreview-v2 を label v1.1.0 統一で比較。

`scripts/compare_phase4_window.py`（Phase 4 標準 BTWindow `phase4-2024H2` train 2016-07..2024-06(carved) / test 2024-07..12・= split_3way デフォルトと一致）。periods 確認: train=2016-07-01..2023-12-31 / calib=2024-01-01..2024-06-30 / test=2024-07-01..2024-12-31。

| モデル | FEATURE | recovery_rate | selected | hit_rate | P/L | pred_rows |
|---|---|---|---|---|---|---|
| **A1 (speedfig 6)** | speed figure 基本6 | **1.176195** | 1924 | 0.1450 | **+33900** | 18737 |
| postreview-v2 (v1.0) | v1.0 デフォルト (speed fig 無し) | 0.766284 | 1741 | 0.1097 | -40690 | 18737 |

- **差 (A1 - postreview-v2) = +0.409912 → A1 が上回る（交代正当）** ✓
- pred_rows=18737 が両者で同一（両 snapshot は行=馬が同一・speed fig 6列の有無のみ差・`_derive_feature_columns(snapshot_id)` で FEATURE 選択）→ **同じ universe で FEATURE 差の純粋比較**。
- label v1.1.0 統一・postreview-v2 の回収率 0.766 は A0（postreview-v2・BT-1・label v1.1.0・0.7308）と同オーダー（v1.0 FEATURE = speed fig 無しを裏付け）。
- **結論**: Phase 4 標準 test 2024下期（本番デプロイ運用窓）で A1 が postreview-v2 を +0.41 で上回る。speed figure 基本6 の効果・is_primary 交代の正当性確認。
- 詳細 JSON: `reports/12-evaluation/phase4-window-a1-vs-postreview-v2.json`

## 5. 手順4: segment dump（ステップ3 精査用）

`FUKUSHO_DEBUG_DUMP_DIR=.planning/debug/a1-primary` で BT-1..5 各窓の full_candidate dump。

| ファイル | size | rows | cols | selected |
|---|---|---|---|---|
| full_candidate_BT-1-30min_before-lightgbm.parquet | 534k | 42214 | 30 | 4359 |
| full_candidate_BT-2-30min_before-lightgbm.parquet | 531k | 41745 | 30 | 4378 |
| full_candidate_BT-3-30min_before-lightgbm.parquet | 529k | 42403 | 30 | 4031 |
| full_candidate_BT-4-30min_before-lightgbm.parquet | 533k | 41745 | 30 | 4308 |
| full_candidate_BT-5-30min_before-lightgbm.parquet | 519k | 41745 | 30 | 4498 |

**受入基準4 PASS**: 5窓分 dump 生成・30列（race_key/umaban/race_date/p_fukusho_hit/fuku_odds/EV/selected/payout/hit 等）。race_key（例 `2023-06-01-01-01`）で n_race join → jyocd/距離/class_name_normalized/is_grade_race/人気 を後付可能（ステップ3 segment 精査用）✓

## 6. 受入基準（検証結果）

1. ✅ A1 が prediction.fukusho_prediction で is_primary=True（他 model_version は False）
2. ✅ load_predictions idempotent（2回で checksum=926aa1ddd82325c5b01d40abdfe62b58 一致）
3. ✅ 切替後バックテスト回収率が Spike 001 と完全一致（5窓・byte-reproducible・切替副作用無し）
4. ✅ full_candidate dump（5窓分）が `.planning/debug/a1-primary/` にあり・segment 精査に使える列構成

## 7. 成果物

- `scripts/save_primary_prediction.py`（A1 予測生成+保存・Phase 4 標準 chain・生産スクリプト不変更）
- `scripts/switch_primary_model.py`（is_primary 切替・D-10 --dry-run/--confirm）
- `scripts/compare_phase4_window.py`（Phase 4 標準窓 A1 vs postreview-v2 比較）
- `reports/12-evaluation/ablation-a1-bt{1..5}-postswitch.json`（切替後 BT・Spike 001 一致）
- `reports/12-evaluation/phase4-window-a1-vs-postreview-v2.json`（手順3b・完了後）
- `.planning/debug/a1-primary/full_candidate_BT-{1..5}-*.parquet`（ステップ3 segment 精査用）

## 8. 結論

A1（speed figure 基本6・binary・label v1.1.0）を新 universe v1.1.0 の主モデル（is_primary）に切り替え完了。Spike 001 の黒字性（5窓平均回収率 1.14）は byte-reproducible で再現され・is_primary 切替の副作用無しを確認。Phase 11/12 reports は v1.0.0 バグ universe のプロビジョナルのまま凍結維持（本 A1 が新 universe 正準ベースライン）。次ステップ（segment 精査）は `.planning/debug/a1-primary/` の dump で実施可。
