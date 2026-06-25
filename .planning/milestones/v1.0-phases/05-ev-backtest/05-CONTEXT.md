# Phase 5: EV & Backtest - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

両モデル（lightgbm/catboost）のキャリブレーション済み予測 `p_fukusho_hit` と複勝オッズ下限/上限から、**固定 `odds_snapshot_policy`（JODDS 発走30分前/10分前）** で `EV_lower`/`EV_upper`・推奨ランク（§11.5）を算出し、**race_id-grouped 時系列（§15.4）** で固定ルール（§11.4 `fukusho_ev_v1`）の仮想購入 backtest を **BT-1..5 × {30min_before, 10min_before} × 両モデル のフル行列** で実行すること。返還/競走中止/dead-loss の **honest 会計（§11.6）** で回収率/P/L/max drawdown/selected_count/effective_bet_count/refund_count を `backtest_strategy_version` stamp 付きで計算し、**全候補を一括報告**（後知恵オッズ選択で回収率を膨らませない・BACK-04）。Build-Order DAG step 6（EV/backtest）。

Phase 4 予測を消費するが、BT窓（test 2023/2025 等）の予測は未生成のため**BT窓ごとに train 期間を変えて再学習**して test 予測を再生成する（Phase 4 `src/model/orchestrator.py` を BT窓で回す）。結果は Phase 6（評価ゲート・主モデル確定）・Phase 7（提示）に引き渡す。

**境界＝検証ゲート。** 確率品質受入基準の検証（Phase 6）・Streamlit/CSV 出力（Phase 7）・対抗的監査テスト（Phase 8）は明示的に後続。Phase 5 は backtest 結果テーブルの定義と書込まで（UI/CSV 出力は Phase 7）。

### ⚠ JODDS 取得進行中（実データ backtest 実行の前提・§19.1 聖域）
`odds_snapshot_policy` の正は EveryDB2 の時系列オッズ（`public.n_jodds_tanpuku`）。ユーザーが 2026-06-20 に取得を開始（過去遡及・2015年から進行中・2026-06-20 時点で 48,432 行・分単位粒度）。**backtest 実行（実データ）は BT期間 2019-2025 の JODDS 取得完了後**。ただし Phase 5 の実装（コード・単体テスト・合成データ検証）は並行で進められる。これは STATE.md の未解決 blocker（「odds-snapshot timing granularity」）を解消する決定。

</domain>

<decisions>
## Implementation Decisions

### オッズ時点ポリシー（EV / BACK-04・Core Value 直結）
- **D-01: `odds_snapshot_policy` に JODDS（時系列オッズ単複・`public.n_jodds_tanpuku`）を採用** — 発走30分前/10分前を再現（§15.5 準拠・`policy='30min_before'`/`'10min_before'`）。`DataKubun='1'`(中間・発走前時系列) を主使用（`3`最終/`4`確定 は補助）。ユーザー選択: JODDS 取得を開始（過去遡取可能と判断・「単複の時系列オッズは取得可能」）。これにより STATE.md blocker 解消。確定オッズのみ（当初案）は却下。**※ §11.2「最終オッズを意思決定オッズとして無条件に使うこと」禁止は、発走前時点を固定 policy として事前登録することで履行**（後知恵ではない）
- **D-02: 時点選択ルール = backward 最近接** — 発走時刻-N分「以下」の直近 `HappyoTime`（`merge_asof(direction='backward')` と同一思想・未来リーク構造的に不可・§13 PIT 原則）。当該時刻以前に1件も無ければ no_bet（§11.3）。特殊値（`----`発売前取消/`****`発売後取消/`0000`無投票/`0999`99.9倍以上）も no_bet。Claude 裁量（Core Value 準拠・ユーザー委任）

### BT窓と再学習ループ（BACK-01 / BACK-04・Core Value「全候補一括報告」）
- **D-03: §15.5 完全準拠フル行列** — BT-1..5 × {`30min_before`, `10min_before`} × {lightgbm, catboost} ≈ 20 backtest。各 BT窓で train 期間を変えて**再学習**（Phase 4 `src/model/orchestrator.py` を BT窓で回す・train 期間は固定 snapshot `postreview-v2`（全期間 PIT-correct）から race_date で filter）。ユーザー選択: 要件の全候補を比較（Core Value 完全履行・後知恵 winner 単独報告禁止も完全）。（代表窓縮小・Phase 4 モデル固定は却下）

### BL-3 投資ROI比較（MODL-02 引き継ぎ・Phase 4 D-07 履行）
- **D-04: BL-3 投資ROI比較を実装** — BL-3（確定複勝オッズが低い=人気順）で固定ルールの仮想購入 → 回収率を主モデル2つと比較。「市場人気戦略 vs AI穴馬志向」の honest 対比。ユーザー選択: 比較する（Phase 4 D-07 履行）。選択ルール（BL-3 は p=1/odds で EV 自己参照=1.0 になるため EV でなく**人気順等で選ぶ**）→ Claude 裁量

### 返還・中止会計（BACK-02 / BACK-03・Core Value「honest」）
- **D-05: 返還・中止会計は Claude 裁量** — §11.6（取消/除外=返還 `effective_stake=0`・競走中止=loss `effective_stake=100`）+ JRAルール（複勝不成立=返還・特別払戻は公式に従う）+ `label.fukusho_label`（`is_scratch_cancel`/`is_race_cancelled`/`is_race_excluded`/`is_dead_loss`/`is_fukusho_sale_available`/`fukusho_payout_places`）と `public.n_harai`（`HenkanFlag2`/`HenkanUma1..28`/`FuseirituFlag2`/`TokubaraiFlag2`/`PayFukusyoPay1..5`）のデータ経路で設計。ユーザー選択: お任せ。対抗的テストで 通常/取消/除外/中止/不成立/同着 各シナリオの `stake`/`payout` を assert（BACK-03 検証ゲート・success criteria #4）

### Claude's Discretion（研究者/計画者に委ねる）
- **BT窓定義の厳密適用** — §15.5 BT-1(train 2019-06〜2022/test 2023)・BT-2(...〜2023/test 2024)・BT-3(...〜2024/test 2025)・BT-4(直近3年 rolling/翌年)・BT-5(直近5年 rolling/翌年)。Phase 3 D-09 の train 2016H2〜 と§15.5 の 2019-06〜 の開始年差は **§15.5（要件正）を優先**。BT-1..3 expanding vs BT-4/5 rolling の実装
- **category_map の BT窓再 fit** — 各 BT窓の train 期間のみで `fit_category_map`（test 窓 ID の train 漏洩防止・§14.3）。Phase 3 固定 map（全期間 train 2016-2023 fit）は参考・BT窓ごとに再 fit がリーク防止上 正しい方向で研究者が実データで確定
- **calib slice の BT窓内 train 尾 carve** — Phase 4 パターン（`max(train.race_date) < min(calib.race_date)` ValueError guard・calib sample <1000 件は sigmoid）
- **EV_lower/EV_upper 計算（§11.1）・推奨ランク（§11.5 S/A/B/C/D）の実装** — EV/確率/odds_lower のみ使用（未定義の予測信頼度不使用）
- **仮想購入ルール（§11.4 `fukusho_ev_v1`）の実装** — EV_lower≥1.05, p≥0.15, odds_lower≥1.5, 同一レース上位2頭, 100円/候補, 複勝のみ。top-2 タイブレーク（同 EV 時の順位付けルール）
- **backtest 結果の永続化** — `backtest` スキーマに結果テーブル新設（staging-swap idempotent load・provenance: `backtest_strategy_version`/`odds_snapshot_policy`/`train_period`/`test_period`/`model_type`/`model_version`）。`settings.py` に `db_schema_backtest` 追加・etl ロール search_path/GRANT 拡張・`schema.py` にテーブル DDL。OUT-02 CSV は Phase 7 だが **DB テーブルは Phase 5**
- **reports/05-backtest.{md,json} 慣例** — Phase 4 の `04-eval.{md,json}` パターン踏襲
- **回収率計算（§11.6）** — 表示オッズでなく実際の払戻金（`PayFukusyoPay`）。max drawdown/effective_bet_count/refund_count/selected_count（§11.4 保持項目）
- **`odds_snapshot_at`/`odds_source_type`/`odds_missing_reason` 保持**（§11.2）

### Folded Todos
（fold せず — 下記 Reviewed Todos 参照）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §11.1-11.6 — EV計算(`EV_lower=p×odds_lower`)/オッズ時点固定(`odds_snapshot_policy`)/欠損 `no_bet`/仮想購入ルール `fukusho_ev_v1`/推奨ランク(S-A/B/C/D)/回収率計算(`effective_stake`)。EV-01/02・BACK-02/03/04 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §15.4-15.5 — バックテスト分割（race_id-grouped 時系列・train/test またぎ禁止）・BT-1..5 窓定義・各BT `odds_snapshot_policy`(30/10分前) 比較。BACK-01/04 の根拠
- `docs/keiba_ai_requirements_v1.3.md` §16.2 — バックテストCSV schema（OUT-02・Phase 7 割当だが DB テーブル設計の参考: backtest_id/strategy_version/train_period/validation_period/odds_snapshot_policy/race_id/horse_id/selected_flag/stake/refund_flag/payout_amount/profit/fukusho_hit_validated/recommend_rank/EV_lower/EV_upper）
- `docs/keiba_ai_requirements_v1.3.md` §19.1 — 再現性（`backtest_strategy_version`・`odds_snapshot_policy`・snapshot policy の保存）
- `docs/keiba_ai_requirements_v1.3.md` §10.6・Out of Scope — 競走中止の backtest 除外禁止（実運用の負けを消して回収率過大評価になるため）・後知恵オッズ時点選択禁止（11.2/15.4）

### EveryDB2 公式マニュアル（実データ依存の正・D-01/D-05 の核心）
- `docs/everydb2/47-JODDS_TANPUKU.md` — **時系列オッズ単複**（`HappyoTime`=発表月日時分 mmddHHMM・`DataKubun`・`FukuOddsLow`/`FukuOddsHigh`・特殊値）。D-01/D-02 オッズ時点の正
- `docs/everydb2/46-JODDS_TANPUKUWAKU_HEAD.md` — **時系列オッズヘッダ**（`DataKubun`: 1中間/2前日売最終/3最終/4確定/9レース中止・`FukuChakuBaraiKey` 払戻対象数 0/2/3・`FukusyoFlag` 複勝発売有無 0/1/3/7・`TorokuTosu`/`SyussoTosu`）
- `docs/everydb2/05-HARAI.md` — **払戻**（`DataKubun`・`FuseirituFlag2`複勝不成立・`TokubaraiFlag2`特別払戻・`HenkanFlag2`/`HenkanUma1..28`返還馬ビットマスク・`PayFukusyoUmaban1..5`/`PayFukusyoPay1..5`/`PayFukusyoNinki1..5` 払戻対象馬/金額/人気）。D-05 返還会計の正
- `docs/everydb2/15-ODDS_TANPUKU.md` — 確定オッズ単複（BL-3 用・`FukuOddsLow`/`High`・特殊値 `----`/`****`/`0000`/`0999`）
- `docs/everydb2/03-RACE.md` — レース（`HassouJikoku` 発走時刻・JODDS `HappyoTime` との差で「N分前」算出の正）
- `docs/everydb2/04-UMA_RACE.md` — 出走馬（`KakuteiJyuni` 着順・`Ninki` 人気・BL-2 用）
- `docs/everydb2/INDEX.md` — テーブル一覧（47/46 JODDS の特定に使用）

### 前フェーズ成果（引き継ぎ決定の正）
- `.planning/phases/04-model-prediction/04-CONTEXT.md` — **D-03(両モデル backtest・Phase 6 まで主モデル確定しない)**/D-05(prediction テーブル)/D-07(BL-3 betting ROI=Phase 5)/D-08(確定オッズ/確定人気) が Phase 5 前提。入力 snapshot `20260620-1a-postreview-v2`(62 feature・SHA256 `26c685f0…ecbdd2`)
- `.planning/phases/03-as-of-features-snapshots/03-CONTEXT.md` — D-09(train 2016H2-2023/val 2024・2025-26 温存) が BT窓設計の前提。固定 snapshot は全期間 PIT-correct
- `.planning/phases/02-fukusho-labels/02-CONTEXT.md` — D-03(`is_model_eligible` フィルタ)・D-04(競走中止=学習0・取消/除外=対象外=返還)。backtest の的中判定・適格性の前提

### コード契約（実装済み・Phase 5 が消費・scout 確認済み）
- `src/model/orchestrator.py` — `train_and_predict`（train→predict→calib）。BT窓で再学習ループ（D-03）の拡張対象
- `src/model/predict.py` — `PREDICTION_COLUMNS`・`MODEL_TYPE_TO_SHORT`（lightgbm→lgb/catboost→cb）。両モデル予渓の区別
- `src/db/prediction_load.py` — `load_predictions`（model_version-scoped staging-swap・idempotent）。backtest 書込の参考
- `src/utils/group_split.py` — `race_id_time_series_split`（expanding・gap なし・race_id disjoint + strict chronological guard）+ `mlxtend.GroupTimeSeriesSplit` re-export。**BT-1..5 固定/rolling window を返すヘルパ（20行・CLAUDE.md 記載）を新設**
- `src/db/schema.py` — `SCHEMAS = [...,"backtest"]`（backtest 層は CREATE SCHEMA のみ・テーブル DDL/GRANT 無し）。backtest テーブル DDL 新設 + GRANT
- `src/db/connection.py` — `make_pool(role='readonly'|'etl')`。**backtest スキーマは search_path/GRANT 未設定** → 拡張必要
- `src/model/baseline.py` — `fetch_market_data`（`n_odds_tanpuku` × `n_uma_race` JOIN・BL-3 市場参照）。JODDS 取得クエリの参考（JOIN PK 同様・6列 PK + umaban）
- `src/etl/fukusho_label.py` — `label.fukusho_label` DDL・`_idempotent_load`（advisory lock staging-swap）。backtest 結果書込に再利用
- `src/etl/normalize.py` — `normalized.n_uma_race`（`odds`/`ninki` 確定値）
- `src/config/settings.py` — `Settings`（`db_schema_backtest` 未定義 → 追加必要・reader ロール `keiba_readonly`）
- `CLAUDE.md` — §11.2 odds policy 固定・§13 PIT（`merge_asof backward`）・リーク防止プリミティブ・stack patterns

### データ資産（Phase 5 入力の正）
- `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet` — 固定 feature matrix（全期間 PIT-correct・554,267行・BT窓 race_date filter の元）
- `snapshots/category_map_20260620-1a-postreview-v2.json` — frozen category map（BT窓再 fit の参考）
- `prediction.fukusho_prediction` — Phase 4 予渓（val 2024 後半・22,213行/モデル・**BT窓再学習で test 窓予渓を再生成**）
- `public.n_jodds_tanpuku` / `n_jodds_tanpukuwaku_head` — 時系列オッズ（D-01・取得進行中）
- `public.n_harai` — 払戻（D-05 返還/払戻額の正）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/model/orchestrator.py` (`train_and_predict`)** — BT窓で train→predict→calib を回す再学習ループの土台。固定 snapshot から BT窓の train 行を race_date filter して学習・test 行で予測
- **`src/utils/group_split.py` + `mlxtend.GroupTimeSeriesSplit`** — BT-1..5 の固定/rolling window を返すヘルパを新設（CLAUDE.md 記載の20行ヘルパ・`(train_race_ids, test_race_ids)` を返す）。race_id disjoint + strict chronological は既存 guard が保証
- **`src/model/baseline.py::fetch_market_data`** — `n_odds_tanpuku` × `n_uma_race` JOIN（6列 PK + umaban）。BL-3 市場参照と JODDS 取得クエリの参考（JODDS は別テーブルだが JOIN 構造同様・`HappyoTime` で時点 filter 追加）
- **`src/etl/fukusho_label.py` の staging-swap idempotent load** — backtest 結果テーブル書込に再利用（advisory lock・CREATE staging・TRUNCATE・INSERT・rowcount verify・DROP/RENAME swap・GRANT）
- **`src/db/prediction_load.py::load_predictions`** — model_version-scoped staging-swap idempotent load パターン。backtest テーブル書込の直接の参考

### Established Patterns
- **5層スキーマ分離（Phase 3 D-08 + Phase 4 D-05）:** feature=不変 Parquet（学習入力）・prediction/backtest=queryable Postgres（結果層）。Phase 5 は **backtest 層を初めて実装**（prediction 層は Phase 4 実装済み）
- **リーク防止プリミティブ（Phase 1 bootstrap）:** `group_split`(race_id)・`merge_asof`(backward)・`category_map`(frozen)・`cv='prefit'`。BT窓再学習ループで race_id disjoint + strict chronological を保証。JODDS 時点選択も `merge_asof(direction='backward')` で未来リーク防止（D-02）
- **hybrid gate（Phase 1 D-01 / Phase 2 D-02）:** 構造的欠陥=ブロック（pytest/CI fail）・量的異常=参考レポート。BACK-03 返還会計の対抗的テスト（各シナリオ stake/payout assert）・BACK-04 odds policy 固定違反は**構造的ブロック**
- **silent fallback 禁止（Phase 1 D-13 / Phase 3 D-03）:** 欠損 odds は `no_bet` sentinel（§11.3）。特殊値（`----`/`****`/`0000`/`0999`）も `no_bet`。都合の良い別時点への差し替え禁止（§11.2）
- **raw read-only / normalized staging-swap idempotent:** backtest 書込のみ DB へ（staging-swap idempotent）

### Integration Points
- **READ（readonly ロール）:**
  - `prediction.fukusho_prediction`（両モデル予渓・`model_type`/`model_version` 区別）
  - `label.fukusho_label`（的中判定 `fukusho_hit_validated`・適格性 `is_model_eligible`・取消/除外/中止/発売フラグ）
  - `public.n_jodds_tanpuku`/`n_jodds_tanpukuwaku_head`（時系列オッズ・D-01・`HappyoTime` 時点選択）
  - `public.n_harai`（返還/不成立/特別払戻/払戻額・D-05）
  - `normalized.n_uma_race`（`HassouJikoku` 発走時刻・確定 odds/ninki）
  - `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet`（BT窓 race_date filter の元）
- **WRITE（etl ロール・search_path/GRANT 拡張）:**
  - `backtest.<結果テーブル>`（新規・staging-swap idempotent・provenance 列付き）
  - `reports/05-backtest.{md,json}`（Phase 4 の `04-eval` パターン踏襲）
- **CONSUMED BY（下流フェーズ）:**
  - Phase 6（評価ゲート）: 確率品質受入基準で主モデル確定（Phase 4 D-03/D-04）
  - Phase 7（Presentation）: Streamlit/CSV が backtest テーブルを SQL 照会・OUT-02 backtest CSV 出力
  - Phase 8（Adversarial Audit）: BACK-03 返還会計テスト・BACK-04 odds policy 固定・race_id 分離 disjoint・JODDS 時点選択 backward 原則の対抗的監査（TEST-01）

</code_context>

<specifics>
## Specific Ideas

- **JODDS 取得進行中（2026-06-20 開始）** — 過去遡取（2015年から・分単位粒度・`DataKubun` 1中間が主）。backtest 実行は BT期間 2019-2025 の取得完了後。Phase 5 実装（コード・単体テスト・合成データ）は並行で進められる。取得完了タイミングは planner が Phase 5 実行計画（実装先行・実データ検証後実行）に反映
- **Phase 4 予渓は val 2024 後半のみ**（2024-07-06〜12-28・53日・22,213行/モデル）。test 2023/2025 は BT窓再学習（D-03）で再生成。つまり Phase 5 は予測を消費するだけでなく**予渓生成（学習含む）も担う**
- **発走時刻の正** — `normalized.n_uma_race` 系（RACE テーブル `HassouJikoku`）。JODDS `HappyoTime`(mmddHHMM) との差で「発走N分前」を算出
- **払戻額の正** — `PayFukusyoPay` は 100円あたり払戻金。回収率は表示オッズでなく**実際払戻金**（§11.6）。`EV_lower=p×odds_lower` は推奨判定用（保守的下限）・実回収率は `PayFukusyoPay/100`
- **複勝発売なし/不成立** — `is_fukusho_sale_available=false` は予測/購入対象外。`FuseirituFlag2='1'`（複勝不成立）は返還。`FukuChakuBaraiKey`（0発売なし/2着払/3着払）で払戻対象数
- **BT窓 train 開始年** — §15.5 は 2019-06〜（要件正）。Phase 3 D-09 は train 2016H2〜。§15.5 優先（要件が正・CLAUDE.md「要件定義書優先」）
- **両モデル×フル行列の計算量** — BT-1..5×2policy×2モデル ≈ 20 backtest・各 BT窓で再学習（2モデル）。実行時間大だが Core Value 履行のため受容（D-03）

</specifics>

<deferred>
## Deferred Ideas

- **Phase 6（Evaluation & Calibration Gates）:** 確率品質受入基準（Brier/LogLoss/Calibration/`sum(p)`/安定性 by segment）のゲート検証・**主モデル確定（Phase 4 D-03/D-04・Calibration 重視事前登録基準）**。Phase 5 は backtest 結果生成まで
- **Phase 7（Presentation）:** Streamlit での予測/backtest 表示・backtest テーブル SQL 照会・OUT-02 backtest CSV 出力。Phase 5 は backtest DB テーブル定義と書込まで（UI/CSV 出力なし）
- **Phase 8（Adversarial Audit）:** BACK-03 返還会計テスト（各シナリオ stake/payout assert）・BACK-04 odds policy 固定違反検出・race_id 分離 disjoint・JODDS 時点選択 backward 原則・固定 seed 再現性の対抗的監査（TEST-01）
- **発走前オッズの更なる時点比較:** §11.2 将来候補（前日売最終/当日朝9:30/60分前/5分前/締切直前）。Phase 5 は 30/10分前の2本。JODDS 取得が継続すれば将来比較可能

### Reviewed Todos (not folded)
- **`phase3-advisory-hardening.md`**（score 0.6・`todo.match-phase`・キーワード「phase」の表面一致のみ）— Phase 03 code review advisory 4件の hardening。**Phase 3.1 で完了済み**（Phase 4 CONTEXT でも判断済み・commit 7f34785 等・216 tests green）。Phase 5 と無関係のため fold せず

</deferred>

---

*Phase: 5-EV & Backtest*
*Context gathered: 2026-06-20*
