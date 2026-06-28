# Spike Conventions

Spike 001 (ablation-recovery) で確立したパターン・stack。新規 spike は特段の理由がなければこれに従う。

## Stack

- **ハーネス**: `scripts/run_ablation.py`（snap-swap + column-drop の2モード・LightGBM binary・BT-1..5・statement_timeout・no DB writes）。
- **回収率指標**: 12系統一 selector `select_bets(FUKUSHO_EV_V1_THRESHOLDS)` = EV≥1.05∩p≥0.15∩odds≥1.5∩top-2 / 回収率=`sum(payout_amount)/sum(effective_stake)`。
- **回収率 chain**: `run_backtest._run_main_model_backtest` を import 再利用（生産 pipeline と同一・外部参照一致の保証）。

## Structure

- 事前登録: `reports/<phase>-evaluation/ablation-spec.{md,json}` を commit してから実行（後知恵防止）。
- 成果物: `reports/<phase>-evaluation/ablation-results.{md,json}`。
- spike 追跡: `.planning/spikes/<NNN>-<name>/README.md` + `MANIFEST.md`。

## Patterns

- **column-drop は thin script で make_X_y 不改変**: `make_X_y(frame, snapshot_id)` で完全 FEATURE_COLUMNS の X,y を取得（生産と一致・assert 通過・core value 機械保証）→ スクリプト内で `X.drop(columns=<群>)` して実験隔離。生産 primitive に override/抜け道を開けない（adversarial audit 被覆維持）。
- **column-drop の命綱**: フル特徴量（drop 無し）で snap-swap（train_and_predict 使用）と完全一致をクロスチェックしてから本格運用。
- **cross-window 検証**: 単年（BT-1）の黒字は信用しない。BT-2..5（別年・rolling）で頑健性を確認して黒字化宣言。
- **leak 再監査**: 良すぎる結果（回収率>1.0）は PIT・target leakage・odds proxy を再点検 + adversarial test 実行。
- **指標2系統の罠**: 回収率計算式が同一でも selector が違うと直接比較不可（09系 EV≥1.0 のみ vs 12系 3条件+top-2）。全変種を1つの統一 selector で測る。

## Tools & Libraries

- LightGBM（native categorical・seed=42・thread=1・deterministic）・`train_and_predict`/`_run_main_model_backtest` import 再利用。
- statement_timeout: `make_pool(role="readonly", configure=_configure_statement_timeout)` で pool 全 connection に SET（memory: subagent-db-query-statement-timeout）。
- byte-reproducible: FIXED_REPRODUCE_TS・固定 seed・2回実行で一致確認。

## Lessons (Spike 001)

- 「特徴量を足せば足すほど良くなる」は偽。9.1悪化が実例（部分集合で回収率が上がれば引く方向）。
- JRA-VAN コード体系（syubetucd/TrackCD/BabaCD）は CODE.md/code_tables.yaml が不正確（[[jra-van-syubetucd-age-not-class]]・[[jra-van-babacd-trackcd-code-system]]）。実データで column_name 等の正確な意味を確認する。
- label 再生成で universe が変わる → 過去レポートは label_version で区別・陳腐化に注意（[[jra-van-syubetucd-age-not-class]]）。
