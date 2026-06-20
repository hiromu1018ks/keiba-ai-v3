# Phase 4: Model & Prediction - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

odds 非依存の Phase 1-A 特徴量（stamped Parquet snapshot のみ）から、キャリブレーション済み `p_fukusho_hit` を算出すること。Build-Order DAG の step 5（モデル・予測）。Phase 2 ラベル（`fukusho_hit_validated`）と Phase 3/3.1 特徴量（PIT-correct feature matrix + 不変 Parquet snapshot + frozen category map）の上に乗り、Phase 5（EV/backtest）が消費する予測を届ける。具体的には：

1. **両モデル学習 + 予測（MODL-01 / §14.1 / SC#1）** — LightGBM 4.6 + CatBoost 1.2.10 を stamped Parquet snapshot **のみ**で学習（live DB 非使用）。`fukusho_hit_validated` を目的変数に、`is_model_eligible`/`label_validation_status` でフィルタ。両モデルの `p_fukusho_hit` を provenance（`model_version`/`model_type`/`feature_snapshot_id`/`as_of_datetime`）付きで出力
2. **ベースライン比較表（MODL-02 / §14.2 / SC#2）** — BL-1（頭数別一定）〜BL-5（LightGBM最小特徴量）を主モデルと並べて評価し「AI モデルが単純モデル・市場参照に付加価値を持つか」を比較表で回答
3. **リークセーフ カテゴリ・欠損処理（MODL-03 / §14.3-14.5 / SC#3）** — LightGBM native categorical（非負 code・`__MISSING__`/`__UNSEEN__`・target encoding 禁止）・CatBoost `cat_features` + `has_time=True`（Pool は `race_start_datetime` sort）。leak diagnostic（rare category が自身の label に一致せず平均に縮む）で target encoding 非混入を検証
4. **時系列キャリブレーション + 再現性（SC#4 / §15.2-15.3）** — `CalibratedClassifierCV(cv='prefit', method='isotonic')` を train より厳格に未来の disjoint slice で fit（`max(train.race_date) < min(calib.race_date)` を ValueError guard で保証・<1000件は sigmoid）。固定 seed → 再実行で同一予測の reproduce smoke test

**境界＝検証ゲート。** EV 計算・仮想購入 backtest・確率品質受入ゲート・Streamlit/CSV は明示的に後続フェーズ（Phase 5/6/7）。Phase 4 は「両モデルのキャリブレーション済み予測 + ベースライン比較表 + リーク防止実証」まで。主モデルの1つ確定も Phase 6 評価ゲートに委ねる（D-03）。

### ⚠ 入力 snapshot の正（researcher/planner 必読・§19.1 聖域）

PROJECT.md / STATE.md は `20260619-1a-v3`（63 feature・fa 0.2.0）を指すが、これは **本日（2026-06-20）の commit 以前**の版。本日の「snapshot 直列化 bug 2件修正」(92e1310)・「feature_availability schema_version 0.3.0 bump」(ef635b6)・「SHA256 drift 対策」(e5a75e2) を取り込んだ **最新版 `20260620-1a-postreview-v2`（62 feature・fa 0.3.0・`byte_reproducible_scope=parquet_data_only_metadata_excluded`）が Phase 4 の正の入力**（D-01）。文書の v3 参照はドリフト → Phase 4 で PROJECT.md/STATE.md を修正。

</domain>

<decisions>
## Implementation Decisions

### 入力 snapshot の確定（§19.1 再現性＝聖域）
- **D-01: Phase 4 入力 snapshot の正 = `20260620-1a-postreview-v2`** — feature_count=62・fa_version 0.3.0・row_count 554,267・SHA256 `26c685f0…ecbdd2`・train 2016-07-01/2023-12-31・val 2024-01-01/2024-12-31。本日の直列化 bug 修正 + schema 0.3.0 + SHA256 scope 修正（metadata除外）取り込み済み。予測 provenance の `feature_snapshot_id` stamp もこれに統一。ユーザー選択: postreview-v2 を正とする。PROJECT.md/STATE.md の v3(63・fa0.2.0) 参照は Phase 4 で修正（ドリフト解消）
- **D-02: feature 63→62 の差は研究者が git + 実データで確定** — `feature_availability.yaml` の git diff(0.2.0→0.3.0) と両 Parquet カラム diff で 63→62 で変わった feature を特定し、Phase 1-A odds-free allowlist 違反がないか検証。確定後 Phase 4 feature 仕様に固定。ユーザー選択: 研究者が確定

### 主モデルと下流への引き渡し（MODL-01/02 / SC#2）
- **D-03: 主モデル確定は Phase 6 評価ゲートまで委ねる** — Phase 4 は LightGBM・CatBoost 両方を学習 + キャリブレーション + 比較表まで。Phase 5 は**両モデルを backtest**（2x workload 受容）。Phase 4 で選定基準を事前登録し、後知恵による基準すり替えを回避。ユーザー選択: Phase 6 まで確定しない。（「Phase 4 で1つ確定」は保守的すぎる・「LightGBM デフォルト」は事前登録薄い、を却下）
- **D-04: 主モデル選定基準 = Calibration 重視（事前登録）** — 信頼性曲線・`sum(p)` 分布の理論値適合（§15.2）・Brier Score の calibration 成分を最優先。EV 整合性＝Core Value に直結するため。判別力（AUC 等）は次点。具体的な重み/閾値は Phase 4 計画で固定し結果を見る前に確定。ユーザー選択: Calibration 重視

### prediction 成果物の永続化（5層スキーマ・§12.1）
- **D-05: 予測は `prediction` DB テーブルに永続化** — `model_type`/`model_version`/`race_id`/`horse_id`/`p_fukusho_hit`/`as_of_datetime`/`feature_snapshot_id`/`calib_method` 列を持つテーブルを `prediction` スキーマに新設。staging-swap idempotent load（Phase 1-2 パターン再利用）・provenance 列で §19.1 再現性。ETL ロールに `prediction` スキーマ `USAGE+CREATE` GRANT 拡張が必要。分離原則: **feature=不変 Parquet（学習入力）・prediction/backtest=queryable Postgres（結果層）** — これが 5層スキーマの意図する分離で Phase 3 D-08（feature 層は Parquet のみ）と整合。Phase 7 Streamlit は SQL で予測を照会。ユーザー選択: prediction DB テーブル
- **D-06: モデル artifact はネイティブ形式** — LightGBM は `booster.save_model`（.txt）・CatBoost は `save_model`（.cbm）・sklearn キャリブレータは joblib → `models/{model_version}/` 配下（`.gitignore` 対象・§19.1 再現性は code + uv.lock + snapshot + provenance）。Phase 3 の pickle-ACE 回避（CR-04/D-04）思想をモデル artifact にも適用（LightGBM/CatBoost ネイティブはバージョン安定・ポータブル）。ユーザー選択: ネイティブ形式

### BL-3 複勝オッズ逆数ベースラインの扱い（MODL-02 / §14.2）
- **D-07: Phase 4 は BL-1..5 全部を実装** — BL-3 は確定複勝オッズの逆数（レース内正規化）を**市場暗示確率ベンチマーク**として LogLoss/Brier/Calibration 比較に使用。§14.2 が明記するとおり「Phase 1-A モデルと同一情報条件の比較ではない」旨を比較表に明記。**モデル特徴量には絶対に混入しない**（MODL-01 odds-free 不変・BL-3 は独立ベンチマークなのでリークなし）。BL-2 は確定人気。betting ROI 比較（固定 snapshot の投資戦略としての BL-3）は Phase 5。SC#2 の比較表を Phase 4 で完成。ユーザー選択: BL-1..5 全部
- **D-08: BL-2/BL-3 の市場データ源 = 確定オッズ/確定人気** — `n_odds_tanpuku`（単複共用・Phase 1 確定事項）の確定複勝オッズと `n_uma_race` 系の確定人気（Ninki）を使用。市場コンセンサス最終値＝確率品質ベンチマークの標準。歴史レース（val 2024 / test 2025-26）に存在。ユーザー選択: 確定オッズ/確定人気

### Claude's Discretion（研究者/計画者に委ねる）
- **train→calib→test の 3way 時系列分割設計** — manifest は train 2016-07〜2023 / val 2024 のみ定義。キャリブレーション用の strict-later disjoint calib slice と最終 test slice（2025-26 は Phase 5 BT 用に温存・Phase 3 D-09）をどこから carve するか（例: train 2016-2022 / calib 2023 / test 2024、または train 2016-2023 / calib 2024前半 / test 2024後半）。`race_id_time_series_split`（expanding window・gap なし）を前提。calib sample <1000 件時の sigmoid 切替判定含む
- **低基数コードの categorical vs numeric 扱い** — `jyocd`/`trackcd`/`sexcd`/`course_kubun`/`class_code_normalized` 等を LightGBM native categorical にするか数値扱いするか。高基数 ID（jockey/trainer/sire/bms/horse）は category_map.py で `_code` int32 化済（確定）。§14.3-14.4 の非負 code・CatBoost `cat_features` 宣言と整合させ研究者が実データで確定
- **early stopping 用 eval set のリーク防止** — LightGBM/CatBoost 訓練時の early stopping eval set を calib/test と分離し、学習用窓内の時系列末尾から切る設計（calib/test に未来情報が漏れないことの unit test）
- **SC#3 leak diagnostic の設計** — 「rare category が自身の label に一致せず平均に縮む」ことを検証する対抗的テスト（target encoding 非混入の実証）。希少カテゴリ合成 → LightGBM/CatBoost の予測が自身の label に過剰適合しないことを assert
- **SC#4 reproduce smoke test の設計** — 固定 seed で再学習→再予測し predictions が bit-identical になることを検証（hash 比較か特定 test race set の予測値比較）。`random_state`/`seed` の全箇所固定
- **ハイパーパラメータ初期値** — 手動（MLflow/Optuna は §21 defer）。LightGBM/CatBoost のデフォルトから妥当な初期値を設定。CLAUDE.md「manual hyperparams」遵守
- **`model_version` 採番方式** — `feature_snapshot_id` と整合する方式（例: `20260620-1a-lgb-v1` / `-cb-v1`）。両モデルを区別する `model_type`（lightgbm/catboost）と組み合わせ

### Reviewed Todos (not folded)
- **`phase3-advisory-hardening.md`**（score 0.6・`resolves_phase: 3.1`・キーワード「phase」の表面一致のみ）— Phase 03 code review advisory 4件の hardening。**Phase 3.1 で既に完了済み**（03.1 D-04・全4 plan 実行済・commit 7f34785 等）。Phase 4 とは無関係のため fold せず。参照のみ。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §14.1-14.5 — 初期モデル（LightGBM/CatBoost/sklearn 系）・目的変数=`fukusho_hit_validated`・ベースライン BL-1..5 定義・LightGBM/CatBoost カテゴリ仕様（target encoding 禁止・負値 code 回避・CatBoost has_time）・欠損理由区別（§14.5 6種）。MODL-01/02/03・SC#2/#3 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §15.1-15.3 — 評価指標（的中率/回収率/Brier/LogLoss/Calibration Curve/安定性）・確率品質受入基準（年別 Calibration 逆転なし・bin 単調増加・ベースライン超過・`sum(p)` 理論値適合 8頭以上2.7-3.3/5-7頭1.8-2.2・中央値/SD/p10/p90）・Calibration 評価軸。SC#4・D-04 選定基準の根拠
- `docs/keiba_ai_requirements_v1.3.md` §11.1-11.2 — EV 計算・オッズ時点固定（Phase 5 用だが BL-3 市場参照の位置づけと整合）。D-07/D-08 の BL-3 境界の根拠
- `docs/keiba_ai_requirements_v1.3.md` §19.1 — 再現性（モデルバージョン・特徴量スナップショット・ラベル定義バージョン・snapshot policy）。D-01/D-05/D-06 provenance の根拠
- `docs/keiba_ai_requirements_v1.3.md` §12.4 — 学習用データセット保存（Parquet・§12.4 メタデータ）。入力 snapshot の契約
- `docs/keiba_ai_requirements_v1.3.md` §17.1-17.3 — スタック（LightGBM 4.6/CatBoost 1.2.10/sklearn 1.9.0）・`src/` レイアウト（`src/model/` 新設想定）・テストコード一覧

### EveryDB2 公式マニュアル（実データ依存の正・ユーザー提供）
- `docs/everydb2/04-UMA_RACE.md` — 出走馬 SE。`Ninki`（人気・BL-2 用）・`KakuteiJyuni`（着順）。BL-2/BL-3 の市場データ源確認に使用
- `docs/everydb2/05-HARAI.md` — 払戻 HR。オッズ関連フィールド（BL-3 用・`n_odds_tanpuku` 単複共用の実態確認）。D-08 の根拠
- `docs/everydb2/INDEX.md` — 全59テーブル+RecordSpec。`n_odds_tanpuku` 等のテーブル/カラム特定
- `docs/everydb2/CODE.md` — ⚠ スクレイピング不完全（Phase 1 D-10）。コード表参照のみ

### プロジェクト計画・状態
- `.planning/ROADMAP.md` — Phase 4 成功基準#1-#4（stamped Parquet のみ学習・BL-1..5 比較表・リークセーフ カテゴリ/欠損・prefit isotonic キャリブレーション + reproduce smoke）・8フェーズ strict DAG
- `.planning/REQUIREMENTS.md` — MODL-01/02/03（Phase 4 割当）・全25要件トレーサビリティ
- `.planning/STATE.md` — Phase 4 移行状態・**⚠ v3 参照ドリフト（D-01 で修正）**・Blockers/Concerns（Phase 5 odds snapshot granularity は BT に影響）
- `.planning/PROJECT.md` — Core Value（リーク防止・再現性＝聖域）・Key Decisions・Out of Scope・**⚠ v3 参照ドリフト（D-01 で修正）**

### 前フェーズ成果（引き継ぎ決定の正）
- `.planning/phases/03.1-timediff-babacd-rolling-restoration/03.1-CONTEXT.md` — **rolling 8系統×3軸=24 + 静的15 + 推定脚質1 + category_map 5列** の feature 構成・3者 parity・silent-NaN regression guard。Phase 4 入力 feature の前提
- `.planning/phases/03-as-of-features-snapshots/03-CONTEXT.md` — **D-03(lookback=直近5走)・D-04(3軸 mean/latest/sd)・D-06(cutoff=race_date-1day)・D-08(Parquet のみ・feature 層なし)・D-09(train 2016H2-2023/val 2024・2025-26 温存)** が Phase 4 分割の前提
- `.planning/phases/02-fukusho-labels/02-CONTEXT.md` — **D-03(`is_model_eligible` フィルタ)・D-04(競走中止=学習0・取消/除外=対象外)**・ラベルテーブル保持項目。Phase 4 目的変数・適格性フィルタの前提

### コード契約（実装済み・Phase 4 が消費）
- `src/utils/calibrator.py` — `fit_prefit_calibrator(base_estimator, X_calib, y_calib, race_dates_calib, train_max_date, method="isotonic")`。FrozenEstimator prefit idiom（sklearn 1.9.0）・train/calib strict-later disjoint を ValueError guard で保証。SC#4 の直接資産
- `src/utils/group_split.py` — `race_id_time_series_split(races, n_splits=5)`（expanding window・gap なし・race_id disjoint + strict chronological + non-empty の3 guard・全 ValueError）。`mlxtend.GroupTimeSeriesSplit` を副 API で re-export。3way 分割の資産
- `src/utils/category_map.py` — `fit_category_map`/`apply_category_map`。`__UNSEEN__`/`__MISSING__` sentinel・非負 int32 保証（NaN→-1 ハザード回避）。高基数 ID の frozen map
- `src/features/category_map_consumer.py` — `build_frozen_category_maps`/`apply_frozen_category_maps`/`persist_category_maps`/`load_category_maps`。train 窓 fit + val/test `__UNSEEN__`/`__MISSING__` 適用。SC#3 の資産
- `src/features/snapshot.py` — `write_snapshot`（byte-reproducible Parquet・SHA256・§12.4 metadata）。モデル artifact の再現性パターンの参考
- `src/features/availability.py` — `load_feature_availability`/`banned_features`/`assert_matrix_columns_registered`。feature allowlist・odds-free 保証（SC#1 間接）
- `src/features/builder.py` / `rolling.py` — feature matrix 構成（入力 Parquet の schema 理解）
- `src/db/schema.py` — `SCHEMAS = ["raw_everydb2","normalized","label","prediction","backtest"]`。`prediction` 層は空（CREATE SCHEMA のみ・テーブル定義なし）。Phase 4 が prediction テーブル DDL を追加
- `src/db/connection.py` — `make_pool(role='etl')`（search_path=label,normalized,public）・`write_cursor`。prediction スキーマ書込には search_path/GRANT 拡張必要
- `src/etl/fukusho_label.py` — `_LABEL_TABLE_COLUMNS`・staging-swap idempotent load パターン（prediction テーブル書込に再利用）
- `src/config/label_spec.yaml` — `fukusho_hit_validated`/`is_model_eligible` フィルタ条件・train period
- `src/config/feature_availability.yaml` — feature 定義・cutoff semantics（fa_version 0.3.0・D-02 差分確認対象）
- `CLAUDE.md` — 技術スタック・リーク防止設定（§14.3/14.4 カテゴリ仕様・§15.2 キャリブレーション・cv='prefit' isotonic・<1000件 sigmoid・manual hyperparams・MLflow/Optuna defer）・プロジェクト指示として权威

### データ資産（Phase 4 入力の正・D-01）
- `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet` — 入力 feature matrix（62 feature・554,267行・SHA256 `26c685f0…ecbdd2`）
- `snapshots/feature_matrix_20260620-1a-postreview-v2.manifest.yaml` — §12.4 メタデータ（feature_snapshot_id/train_period/validation_period/feature_count/fa_version）
- `snapshots/category_map_20260620-1a-postreview-v2.json` — frozen category map（jockey_id/trainer_id/sire_id/bms_id/horse_id の5列）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/utils/calibrator.py` (`fit_prefit_calibrator`)** — そのまま SC#4 キャリブレーションに使用。LightGBM/CatBoost の学習済み estimator を `FrozenEstimator` で包み `CalibratedClassifierCV(cv='prefit', method='isotonic')`。train_max_date < calib_min_date の strict-later 検証内蔵（違反で ValueError）。calib sample <1000 件の sigmoid 切替は呼出側で判定
- **`src/utils/group_split.py` (`race_id_time_series_split`)** — train/calib/test の race_id-grouped 時系列分割に使用。expanding window のみ・gap なし。BT-1..5 の固定/rolling window は Phase 5 だが、Phase 4 の model-dev 3way 分割は本関数で構築。1-2週間 gap はオプション（CLAUDE.md 踏襲可）
- **`src/utils/category_map.py` + `src/features/category_map_consumer.py`** — 高基数 ID（jockey/trainer/sire/bms/horse）の frozen category map。`load_category_maps(snapshots/category_map_20260620-1a-postreview-v2.json)` で val/test を `_code` int32 化（`__UNSEEN__`/`__MISSING__`・非負）。train 窓 fit 済み artifact をそのまま消費（再 fit 禁止）
- **`src/features/availability.py` (`assert_matrix_columns_registered`)** — feature allowlist 検査。BL-3/odds が feature に混入していないことの防御的 assert に流用可（D-07 保証）
- **`src/etl/fukusho_label.py` の staging-swap idempotent load** — `_idempotent_load`（advisory lock・CREATE staging・TRUNCATE・INSERT・rowcount verify・DROP/RENAME swap・GRANT）。prediction テーブル書込に再利用（D-05）
- **`src/features/snapshot.py` の byte-reproducible Parquet** — モデル artifact の再現性設計の参考（決定論的書込・hash）。予測 Parquet（もし作る場合）のパターン

### Established Patterns
- **5層スキーマの分離原則（Phase 3 D-08 + D-05）:** feature=不変 Parquet（学習入力・DB に feature 層なし）・prediction/backtest=queryable Postgres（結果層・Streamlit/CSV が SQL 照会）。Phase 4 はこの分離の prediction 側を初めて実装
- **リーク防止プリミティブ（Phase 1 bootstrap）:** calibrator(cv='prefit')・group_split(race_id)・category_map(frozen)・pit_join(backward)。Phase 4 はこれらを本格消費する最初のフェーズ
- **hybrid gate（Phase 1 D-01 / Phase 2 D-02）:** 構造的欠陥=ブロック（pytest/CI fail）・量的異常=参考レポート。SC#3 leak diagnostic（target encoding 混入）・SC#4 reproduce 失敗は**構造的ブロック**
- **silent fallback 禁止（Phase 1 D-13 / Phase 3 D-03）:** 欠損は `__MISSING__` sentinel・未知 ID は `__UNSEEN__`。LLDB の NaN→-1 依存禁止（§14.3）
- **raw read-only / normalized staging-swap idempotent:** モデル学習は stamped Parquet のみ（live DB 非使用・SC#1）。prediction 書込のみ DB へ
- **native categorical + has_time（CLAUDE.md / §14.3-14.4）:** LightGBM は `category` dtype・CatBoost は `cat_features` + `has_time=True`・Pool は `race_start_datetime` sort。target encoding 一切禁止

### Integration Points
- **READ（readonly ロール・stamped Parquet）:**
  - `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet`（feature matrix・PyArrow/pandas 読込）
  - `snapshots/category_map_20260620-1a-postreview-v2.json`（frozen category map）
  - `label.fukusho_label`（目的変数 `fukusho_hit_validated`・`is_model_eligible`/`label_validation_status` フィルタ・`race_date` 時系列整序）
  - `normalized.n_uma_race` / odds テーブル（BL-2 ninki / BL-3 確定複勝オッズ・`n_odds_tanpuku` 単複共用）
- **WRITE（ETL ロール・search_path 拡張）:**
  - `prediction.<p_fukusho_hit テーブル>`（新規・provenance 列付き・staging-swap idempotent）
  - `models/{model_version}/`（ネイティブ形式 artifact・`.gitignore`）
- **CONSUMED BY（下流フェーズ）:**
  - Phase 5（EV/backtest）: 両モデルの `p_fukusho_hit` を消費・固定 `odds_snapshot_policy` で仮想購入・BL-3 betting ROI 比較
  - Phase 6（評価ゲート）: Calibration/Brier/LogLoss/`sum(p)` 受入基準で主モデル確定（D-03/D-04）
  - Phase 7（Presentation）: Streamlit/CSV が prediction テーブルを SQL 照会
  - Phase 8（adversarial audit）: SC#3 leak diagnostic・SC#4 reproduce・race_id 分離 disjoint・categorical/missing handling の対抗的監査（TEST-01）

</code_context>

<specifics>
## Specific Ideas

- **feature 63→62 の正体（D-02・研究者確定対象）** — fa 0.2.0(v3) → 0.3.0(postreview-v2) で1 feature が変わった。本日の commit ef635b6（schema bump）・92e1310（直列化 bug 修正）が関連。`feature_availability.yaml` git diff + 両 Parquet カラム diff で特定。odds-free allowlist（§13.4/SC#2）違反でないことを検証してから Phase 4 feature 仕様を固定
- **postreview-v2 の SHA256 scope 変更** — v3=`parquet_bytes_only` → postreview-v2=`parquet_data_only_metadata_excluded`（metadata を hash scope から除外）。commit e5a75e2「SHA256 drift 原因判明（識別子列依存）」の対策。モデル再現性検証時の hash 解釈に注意
- **両モデル予測の model_type 区分（D-03/D-05）** — prediction テーブルは `model_type ∈ {lightgbm, catboost}` + `model_version` で両モデルを区別。Phase 5 は両行を backtest。主モデル確定（Phase 6）後に `is_primary` フラグ等で運用可
- **BL-3 のレース内正規化** — 複勝オッズ逆数をレース内で正規化して `sum=払戻対象数`（8頭以上3/5-7頭2）に揃えるか、生の逆数のままで LogLoss 比較するかは研究者が確定（§15.2 `sum(p)` 適合チェックとの整合）。市場暗示確率としての標準的な正規化方式
- **`src/model/` は Phase 4 で新設** — Phase 1-3 は `etl/`/`utils/`/`config/`/`db/`/`features/` のみ。学習/予測/ベースライン/評価モジュールを `src/model/` 配下に配置（§17.2 レイアウト）
- **LightGBM/CatBoost は pyproject.toml に未 pin** — dependencies に `lightgbm`/`catboost` が存在しない。Phase 4 計画で CLAUDE.md 指示版（LightGBM 4.6.0・CatBoost 1.2.10）を pin 追加。sklearn 1.9.0・mlxtend 0.25.0 は既 pin

</specifics>

<deferred>
## Deferred Ideas

- **Phase 5（EV & Backtest）:** 両モデルの `p_fukusho_hit` を消費した EV 計算（`EV_lower`/`EV_upper`）・推奨ランク・race_id-grouped 仮想購入シミュレータ（固定 `odds_snapshot_policy` 30/10分前・返還/競走中止の `effective_stake`）・BT-1..5 フル行列・BL-3 の betting ROI 比較。Phase 4 は確率品質比較表まで
- **Phase 6（Evaluation & Calibration Gates）:** 確率品質受入基準（Brier/LogLoss/Calibration/`sum(p)`/安定性）のゲート検証・**主モデル確定（D-03/D-04・Calibration 重視事前登録基準）**。Phase 4 は基準の事前登録と両モデル予測の生成まで
- **Phase 7（Presentation）:** Streamlit での予測一覧表示・prediction テーブルの SQL 照会・予測/backtest CSV 出力。Phase 4 は prediction テーブル定義と書込まで（UI なし）
- **Phase 8（Adversarial Audit）:** SC#3 leak diagnostic（target encoding 非混入）・SC#4 reproduce smoke・race_id 分離 disjoint・categorical/missing handling・固定 seed 再現性に対する対抗的監査（TEST-01）。Phase 4 で実装する leak diagnostic/reproduce 機構が監査対象
- **Optuna ハイパラ最適化（将来）:** Phase 4 は手動ハイパラ（§21 defer）。評価/特徴量安定後に Optuna 導入を再評価

### Reviewed Todos (not folded)
- **`phase3-advisory-hardening.md`** — Phase 03 code review advisory 4件（WR-01'/WR-02/CR-01新/WR-03）の hardening。**Phase 3.1 で完了済み**（03.1 D-04・commit 7f34785 等・216 tests green）。Phase 4 と無関係のため fold せず（todo.match-phase のキーワード「phase」表面一致のみ・score 0.6）。

</deferred>

---

*Phase: 4-Model & Prediction*
*Context gathered: 2026-06-20*
