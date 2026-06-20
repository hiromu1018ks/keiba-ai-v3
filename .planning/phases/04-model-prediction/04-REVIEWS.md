---
phase: 4
reviewers: [codex]
reviewed_at: 2026-06-20
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
  - 04-05-PLAN.md
  - 04-06-PLAN.md
model_invoked: codex (gpt-5.5, codex-cli v0.139.0)
cycle: 4
cycles:
  - cycle: 1
    reviewer: codex (gpt-5.5, codex-cli v0.139.0)
    reviewed_commit: 56c969a
    status: ACTIONABLE — 再計画推奨（HIGH 19件未解決）
  - cycle: 2
    reviewer: codex (gpt-5.5, codex-cli v0.139.0)
    reviewed_commit: 2455424
    status: ACTIONABLE — 大幅改善・Cycle 1 HIGH 14/19 FULLY RESOLVED・NEW HIGH 1件（CatBoost 予測整列 API 接続）残存
  - cycle: 3
    reviewer: codex (gpt-5.5, codex-cli v0.139.0)
    reviewed_commit: 7214287
    status: CONVERGED — Cycle 2 の6件中5件 FULLY RESOLVED・NEW HIGH-1 エンドツーエンド閉塞・残存 HIGH 0件・actionable MEDIUM 1件 + LOW 3件（Phase 4 実装進行可能）
  - cycle: 4
    reviewer: 自己収束（user-authorized beyond MAX_CYCLES=3・Cycle 3 actionable 4件の PLAN/doc 反映確認）
    reviewed_at: 2026-06-20
    status: FULLY CONVERGED — Cycle 3 の4件（NEW-M1 MEDIUM・NEW-4 残渣 LOW・NEW-L1 LOW・NEW-L2 LOW）を全て PLAN/doc に組み込み・actionable=0 達成
status: CONVERGED — Cycle 4 完了・残存 HIGH 0件・actionable 0件・execute-phase 進行可能（Cycle 3 の4件 MEDIUM/LOW は Cycle 4 で PLAN/doc に組み込み済）
---

# Cross-AI Plan Review — Phase 4（Model & Prediction）

本レビューは Codex（gpt-5.5 / codex-cli 0.139.0）による Cycle 1 単独レビューです。Gemini/Claude CLI は未検出／自己除外のため Codex のみ起動。Phase 4 は本プロジェクトで最もリーク感受性の高いフェーズであり、リーク防止正確性・再現性・ゴール整合性・ゴールバックワードの4軸で査読しました。全指摘は日本語で記述し、深刻度（HIGH/MEDIUM/LOW）付きでPLAN.md単位＋クロスプランに分類しています。

---

## Codex Review

### 04-01 — 基盤（依存ライブラリ pin・prediction DDL/GRANT・RED stub・ドリフト修正）

#### Summary
依存ライブラリ固定、prediction スキーマ、GRANT、RED テストスタブ、snapshot 文書ドリフト修正という基盤計画としては妥当。主なリスクは live DB 状態を変更し、Phase 4 の安全性を証明できる範囲を超えた RED テストを「安全性確保済み」と見せかける点。大部分はインフラであり、リーク防止そのものはまだ始まっていない。

#### Strengths
- `lightgbm==4.6.0` / `catboost==1.2.10` を固定しスタック再現性を直接担保
- `prediction.fukusho_prediction` を早期に定義し後続コードの契約を具体化
- SC#1/#3/#4/MODL-02 の検証契約を RED テストとして明示（受入基準の曖昧さを排除）
- 危険な `20260619-1a-v3` vs `20260620-1a-postreview-v2` 文書ドリフトを修正

#### Concerns
- **HIGH — DDL 主キーが `feature_snapshot_id` と `as_of_datetime` を含まない。**  
  `PREDICTION_TABLE_DDL` の PK は `(model_type, model_version, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)`。`model_version` を異なる snapshot や再実行タイムスタンプで誤用した場合、staging-swap が履歴を不可視に上書きする。provenance 聖域（§19.1）を弱体化させる。
- **MEDIUM — `search_path` 拡張が書込曖昧性を生む。**  
  ETL `search_path` に `prediction` を追加するのは便利だが、prediction 書込は明示的にスキーマ修飾する方が安全。search_path 変更はテーブル名の誤りを隠蔽しうる。
- **MEDIUM — RED stub 件数の不整合リスク。**  
  計画は「13+ tests」と書くが、列挙された stub は 4+4+3+6+2+1=20 件。「13 failed」を期待する受入基準は陳腐化しており、不完全なテスト作成を正当化しうる。
- **MEDIUM — `uv add` / live DB スキーマ適用が再現性中立でない。**  
  `uv.lock` diff と `run_apply_schema.py` の冪等性を確認すべき。受入基準に「意図しない依存アップグレード無し」の明示がない。
- **LOW — `tests/model/__init__.py min_lines: 1` が「空パッケージマーカー」と矛盾。**

#### Suggestions
- `feature_snapshot_id` を PK または `model_version` に紐付く一意性/CHECK 制約に含める
- search_path を拡張しても全 prediction 書込は明示的にスキーマ修飾 SQL にする
- テスト件数の受入基準を実 stub 件数（20件）に修正
- `uv lock --check` または diff 検査を追加し LightGBM/CatBoost と必要な推移依存のみ変更されたことを保証
- DB CHECK 制約を追加: `p_fukusho_hit BETWEEN 0 AND 1`、`model_type IN (...)`、`calib_method IN (...)`

---

### 04-02 — data.py + calibrator.py + artifact.py

#### Summary
SC#1/SC#4 の足場（stamped Parquet・raw ID 除外・時系列分割・prefit キャリブレーション wrapper）として方向性は強い。しかし label join・feature 列と metadata 列の区別・分割妥当性周りに深刻なインターフェース曖昧さがある。

#### Strengths
- `load_feature_matrix()` を Parquet のみ・DB 引数なしに維持
- `fit_prefit_calibrator` を再実装せず薄く wrap
- `assert` ではなく `raise ValueError` の guard を要求（リーク検査として正しい）
- train/calib/test を厳密な時系列スライスとし 2025+ を Phase 5 に温存

#### Concerns
- **HIGH — `prepare_model_matrix(df)` の契約が混乱している。**  
  Task 1 は「上記 join/filter/drop を統合」と書くが、シグネチャは `df` のみ。一方 `join_labels(feature_df, readonly_cur)` は DB アクセスを要する。テストは合成 DataFrame で DB を回避する。この結果「本番コードが label を正しく join していないのにテストが GREEN」になりうる（fake-green）。
- **HIGH — `assert_matrix_columns_registered(spec, X.columns)` が metadata/label 列に誤って呼ばれうる。**  
  `X` が `race_date`/`feature_snapshot_id`/`fukusho_hit_validated`/`sales_start_entry_count` 等を含む場合、allowlist 検査が誤って fail するか、通すために弱体化されるおそれがある。検査前に厳密な feature 列選択を定義しなければならない。
- **HIGH — race ID の定義が不安定。**  
  `race_id` があればそれを使い、無ければ `race_nkey` で代用。既存 Parquet は `race_nkey` を持ち、DB ラベルは複合キーを使う。`race_nkey` が大域一意でない、または日付安定でない場合、disjoint 検査が誤解を招く。
- **MEDIUM — 厳密時系列分割の条件がやや不完全。**  
  受入基準 `train_max < calib_min < calib_max < test_min` は `test_min <= test_max` を欠き、全ケースで `max(calib) < min(test)` を直接 assert しない。
- **MEDIUM — SHA256 検証が過少仕様。**  
  「`26c685f0…ecbdd2`」は略記。実際の guard は manifest から完全ハッシュを取得し、hash scope を明確に定義して検査する必要がある。
- **MEDIUM — artifact 計画が calibrated estimator を曖昧に保存。**  
  `save_native_artifact(model, model_type, ...)` は model_type で保存形式を分岐するが、後続で `calibrator.joblib` を要求する。LightGBM/CatBoost を wrap した sklearn CalibratedClassifierCV は native base estimator とは別物。

#### Suggestions
- データ API を明確に分割: `load_feature_matrix()`、`load_labels(readonly_cur)`、`build_training_frame(feature_df, label_df)`、`make_X_y(frame)`
- `FEATURE_COLUMNS` を registry から明示的に（metadata/raw IDs/labels を除いて）定義
- 正準 `race_key` ビルダを `(year,jyocd,kaiji,nichiji,racenum)` から構築し、ad-hoc な `race_nkey` フォールバックを廃止
- base estimator の native artifact と `calibrator.joblib` を分離保存
- 完全 SHA256 を manifest から読み、Phase 3 と同一の hash scope で検査

---

### 04-03 — trainer.py + baseline.py

#### Summary
本フェーズで最もリーククリティカルな計画。LightGBM 負カテゴリコード・CatBoost `has_time=True`・eval-set リーク・target encoding・BL-3 分離といった主要ハザードを正しく名指ししている。しかし提案された SC#3 rare-category 診断は書かれたままでは不十分であり、CatBoost の高基数 ID 扱いは MODL-03 の核心であるにも関わらず未解決のまま。

#### Strengths
- LightGBM native categorical と CatBoost `has_time=True` を明示的に要求
- early-stopping eval リーク向け `assert_eval_disjoint` を含む
- BL-3 を model feature ではなく market reference として扱う
- BL-2/BL-3 をレース内正規化し `sum(p)` 期待値と整合させる

#### Concerns
- **HIGH — CODE_INT32_COLS の CatBoost 扱いが不正/不完全。**  
  計画は `CODE_INT32_COLS` を「categorical 扱い」と書くが、直後に「CatBoost は `cat_features` に含めず数値扱い（デフォルト）」と述べる。これは MODL-03 の categorical-ID 意図に違反し、CatBoost が任意の ID に序数構造を課す結果になりかねない。
- **HIGH — rare-category leak diagnostic が false-pass しうる。**  
  native tree モデルでも、rare category が train と test の両方に現れ全 positive label なら過剰適合しうる。逆に target encoding は smoothing 次第で >0.5 を必ずしも生成しない。書かれたままのテストは target/mean encoding リークを特異に検出するわけではなく、一つの合成設定下での暗記を検出するに過ぎない。
- **HIGH — テストが低基数列の合成 `RARE_X` を使うが高基数 `_code` 列を検証しない。**  
  最も危険な列は `jockey_id_code`/`trainer_id_code`/`sire_id_code`/`bms_id_code`/`horse_id_code`。SC#3 はこれら `_code` 列の LightGBM/CatBoost 両方の扱いを明示的に問うている。
- **HIGH — CatBoost Pool sort 保証が現テスト設計では強制不能。**  
  `get_all_params()['has_time'] == True` の確認だけでは不十分。`_prepare_catboost_pool` が sort 済み行を受け取り、予測パスも一貫して sort するか元の順序を復元することを検証するテストが必要。
- **MEDIUM — LightGBM categorical code テストが string cat の `.cat.codes.min() >= 0` のみ。**  
  `_code` 列が非負 int32 であり `categorical_feature` に含まれることも assert すべき。
- **MEDIUM — BL-3 が確定オッズ/確定人気を使用。**  
  D-07/D-08 に基づく market reference として妥当だが、比較表は「同一情報集合ではない」警告を不可能なまでに目立たせる必要。prose でやっているが evaluator でも警告を消せないように。
- **MEDIUM — BL-4/BL-5 のキャリブレーションが不明。**  
  SC#2 は確率品質を比較する。未キャリブレーションの BL-5 LightGBM は比較を不公平/ノイズ多いものにしうる。主モデルがキャリブレーションされるなら baselines も同一の未来スライスでキャリブレーションするか、明示的に未キャリブレーションと記すべき。

#### Suggestions
- CatBoost `_code` 扱いを今決定: 非負 code を文字列化して `cat_features` に含めるか、数値扱いを MODL-03 からの意図的逸脱として文書化。推奨は全 categorical ID code を文字列化して CatBoost に渡す
- SC#3 診断を強化:
  - 意図的にリークする target-encoded feature を注入し診断が fail することを証明
  - 高基数 ID 列で rare category を検証
  - test rare category を train-only / test-unseen ケースとし `__UNSEEN__` 縮小を検証
- 明示的テストを追加:
  - `test_lightgbm_code_int32_cols_are_categorical_and_nonnegative`
  - `test_catboost_code_int32_cols_are_cat_features`
  - `test_catboost_predict_preserves_original_row_order_after_sort`
- BL-4/BL-5 をキャリブレーションするか比較表で未キャリブレーションと明記

---

### 04-04 — predict.py + prediction_load.py + evaluator.py

#### Summary
provenance と staging-swap 永続化は強力。evaluator は有用だが Phase 6 的な受入ロジックへ越境しつつ、一部確率品質要件が過少仕様のまま残る。最大の問題は D-10 の model_version 形式例との直接矛盾。

#### Strengths
- 予測出力に必要 provenance 列を含む
- `p_fukusho_hit ∈ [0,1]` と PK 一意性の検証を追加
- 既知の staging-swap パターンを再利用
- evaluator が Brier/LogLoss/AUC/calibration/`sum(p)` を含む

#### Concerns
- **HIGH — model_version 形式が D-10 例と矛盾。**  
  D-10 は例を `20260620-1a-lgb-v1` / `20260620-1a-cb-v1` とするが、本計画の `make_model_version("20260620-1a-postreview-v2", ...)` は `20260620-1a-postreview-v2-lgb-v1` を返す。後続の計画と artifact パスは後者を使い、provenance 期待が壊れる。
- **HIGH — prediction staging-swap が `prediction.fukusho_prediction` 全体を破壊。**  
  LightGBM 予測をロードした後 CatBoost 予測を別個にロードすると、常に統合 DataFrame を渡さない限り2回目の swap が1回目を削除しうる。ローダ契約は「全行置換」「1 model_version の行置換」「Phase 4 全行置換」のいずれかを明示しなければならない。
- **HIGH — `_idempotent_load_prediction` のテーブル swap がインデックス/コメント/GRANT を破壊しうる。**  
  `LIKE INCLUDING ALL` はテーブルコメントを保存せず、制約/インデックス命名問題を生じうる。既存 label パターンは受容されるかもしれないが prediction は長寿命の下流テーブル。partition or model-version scope の置換を検討すべき。
- **MEDIUM — `as_of_datetime = datetime.now()` が bit-identical 出力を損なう。**  
  SC#4 は予測を比較するが、全予測 DataFrame を hash すると実行時タイムスタンプが変わる。決定論的な予測値 hash と provenance タイムスタンプ方針を分離必要。
- **MEDIUM — evaluator `sum(p)` はキャリブレーション済み独立二値確率では自然に逸脱しうる。**  
  複勝確率は馬ごとの二値確率であり払戻対象数に厳密に合計することを制約されない。`sum(p)` 検査は診断として有効だが、直接の正確性として扱うと誤解を招く。
- **MEDIUM — calibration curve テストが binning 契約を欠く。**  
  再現性のため bin 数・strategy・最小 bin count・単調性処理を指定すべき。
- **LOW — 「JSON + Markdown を1つの `.md`」は不格好。**  
  `reports/04-eval.md` と `reports/04-eval.json` に分離が望ましい。

#### Suggestions
- 全計画で単一の `model_version` 規約を実装前に固定
- prediction load の置換 scope を明示:
  - `replace_all_predictions(df)` または
  - `replace_model_version(model_type, model_version, df)`
  Phase 5 では model-version scope の置換が安全
- 揮発性 `as_of_datetime` を再現性 hash から除外するか、reproduce テストでは固定 `as_of_datetime` を渡す
- DB に `CHECK (p_fukusho_hit >= 0 AND p_fukusho_hit <= 1)` を追加
- evaluator 出力で定量的診断と受入ゲートを分離

---

### 04-05 — run_train_predict.py + SC#4 reproduce smoke

#### Summary
全 pipeline を統合し SC#4 を証明しようとする。意図は正しいが、巨大な orchestrator 関数を `src/model/calibrator.py` に置き責任を曖昧にし、`feature_df`/`X`/splits/labels/market data 周りで複数のインターフェース破綻を含む。統合リスクが最も高い計画。

#### Strengths
- LightGBM と CatBoost の両方を end-to-end 実行することを要求
- 正準 snapshot と両 model type の CLI デフォルトを含む
- reproduce 失敗を構造的ブロッカーとして扱う
- artifact・report・prediction-table 出力を要求

#### Concerns
- **HIGH — `train_and_predict` は `calibrator.py` ではなく orchestrator に属する。**  
  data・trainer・predict・artifact 的関心を import し循環依存を生み、キャリブレーション utility を非純粋にする。
- **HIGH — `train_and_predict(feature_df)` が `split_3way(feature_df)` の前に `prepare_model_matrix(feature_df)` を呼ぶが、`prepare_model_matrix` は `(X, y)` を返し split 整合 metadata を保存しない。**  
  計画は `splits["train"]` から `X_train_core` を導出するが index 整合を指定しない。これは典型的な silent leakage / row-mismatch の失敗モード。
- **HIGH — CatBoost sort 済み Pool の予測が元の行順序に戻らない可能性。**  
  訓練時 sort は問題ないが、予測時は sort しないか元の index を復元しなければならない。計画はこれを指定しない。
- **HIGH — artifact save が `result["calibrated"]` を `model_type="lightgbm"`/`"catboost"` で処理する。**  
  `save_native_artifact` は `.txt/.cbm` 向けに native LightGBM/CatBoost base model を期待するが、`result["calibrated"]` は sklearn `CalibratedClassifierCV`。これは fail するか誤ったオブジェクトを保存する公算が大きい。
- **HIGH — reproduce smoke がデフォルトスレッドでは bit-identical にならない公算。**  
  LightGBM には deterministic flags があるが CatBoost CPU 決定論は thread count・data order・logging/eval 挙動に依存しうる。`thread_count=1` を固定するか bit-identical が不可能な場合は許容 tolerance を明示すべき。
- **MEDIUM — `--snapshot-id` が実際にはパスを選択しない。**  
  data 計画は `SNAPSHOT_PATH` を hardcode。CLI は `--snapshot-id` を受け取るが manifest/path への mapping がなければ provenance 文字列に過ぎない。
- **MEDIUM — prediction loader が統合予測でテーブルを置換するため `--model-type lightgbm` が CatBoost 行を削除しうる。**  
  クロスプラン永続化契約の問題。

#### Suggestions
- `train_and_predict` を `src/model/orchestrator.py` に移動するか orchestration を `scripts/run_train_predict.py` のみに留める
- 単一の index 付き modeling frame を split/feature 選択/予測/出力の全段で運び、全 `X/y/race_df` merge の直前に index equality を assert
- artifact を次の形で保存:
  - native base estimator: `lgb_model.txt` / `cb_model.cbm`
  - calibrator wrapper: `calibrator.joblib`
  - metadata: 決定論的 JSON
- reproduce モードで LightGBM に `num_threads=1`、CatBoost に `thread_count=1` を追加
- `--snapshot-id` を manifest/Parquet path/category map path/期待 hash へ解決

---

### 04-06 — 最終検証・ROADMAP 更新

#### Summary
最終ゲートの概念は正しい: 実 pipeline 実行、SC#3/SC#4 証明、validation/roadmap 更新。危険は、モデルが合成テストのみ通過したりテストが skip されても文書完了ステップになりうる点。また SC#3 の「live データ」カバレッジを過大請求する。

#### Strengths
- SC#3 と SC#4 を構造的ブロッカーとして扱う
- 正準 snapshot 上の全 pipeline 実行を要求
- report・model artifact・prediction DB 行・全 pytest suite を検査
- ROADMAP に明示的 SC 達成根拠で更新

#### Concerns
- **HIGH — SC#3 leak diagnostic は合成データであり live-data 証明ではない。**  
  計画は「live データ・両モデルで GREEN」と書くが `test_no_target_encoding_leak` は合成。対抗的 unit testing としては妥当だが、live-data での target encoding 非混入証明と称すべきでない。
- **HIGH — テストが `KEIBA_SKIP_DB_TESTS=1` で skip されうる。**  
  最終ゲートは DB テストが skip されないことを明示的に要求しなければならない。さもなければ prediction-load と market-data source テストが green-by-skip になりうる。
- **HIGH — ROADMAP 更新が SC#2「付加価値あり」を真ではないのに達成扱いしうる。**  
  SC#2 は比較表が「AI が付加価値を持つか」に答えることを求める。計画は表の存在を保証するがモデルが baselines を上回ることは保証しない。Phase 4 ゴールは「model adds measurable value」であり、結果が劣るなら「付加価値未証明」の注記無しに成功宣言すべきでない。
- **MEDIUM — 全テスト suite 実行時間 `<120s` は CatBoost/LightGBM と pipeline テストが走れば非現実的。**  
  重要なテストを縮小/skip する圧力を生じうる。
- **MEDIUM — validation 文書が失敗ゲート後にも手動更新されうる。**  
  `04-VALIDATION.md` にコマンド出力や checksum を格納することを要求すべき。
- **MEDIUM — 「progress.completed_plans = 23」は脆いプロジェクト管理算術。**  
  drift しうる、技術的正確性と無関係。

#### Suggestions
- 最終ゲートは `KEIBA_SKIP_DB_TESTS` を unset で実行し、Phase 4 critical テストの skipped count = 0 を記録
- validation にコマンド・終了コード・予測 checksum・artifact hash・行数の証拠を格納
- ROADMAP で次を区別:
  - 「SC#2 比較表生成済み」
  - 「AI が BL-x を明白に上回る」
  baselines に勝たない場合、Phase 4 は有効な否定的結果を生成できるが model value を請求すべきでない
- 合成 SC#3 を「live データ」証明と呼ばず、対抗的構造診断と呼ぶ

---

## Cross-Plan Concerns（複数 PLAN にまたがる統合懸念）

### 1. Model Version Drift
D-10 例は `20260620-1a-lgb-v1` / `20260620-1a-cb-v1` だが、後続計画は `20260620-1a-postreview-v2-lgb-v1` を使う。artifact・prediction 行・テスト・ROADMAP 証拠に影響。単一規約を固定すべき。

### 2. CatBoost 高基数 ID が未確定
`CODE_INT32_COLS` は SC#3 の核心。計画は繰り返し categorical と書くが CatBoost は `cat_features` に入れない限り数値扱いする。これはリーク/意味論リスクであり MODL-03 のゴール整合性 gap。

### 3. テーブル置換 Scope が危険
`prediction_load.py` は prediction テーブル全体を置換しうる。全実行が全 model type/version の全希望行を常に供給する場合のみ安全。CLI は単一 model 実行を許すため全テーブル置換は有効な予測を削除しうる。

### 4. Row Alignment が過少仕様
全 pipeline は `feature_df`/`X`/`y`/split frame/sort 済み CatBoost Pool/予測 frame を繰り返し変換する。安定した index 検査がなければ、予測が誤った馬に書き込まれてもテストが GREEN のままになりうる。

### 5. 再現性が完全に bit-identical でない
seed は固定だが bit-identical 再現性には更に以下が必要:
- 固定 thread count
- 安定した sort kind
- 決定論的 categorical 順序
- 固定 `as_of_datetime` または hash からの除外
- 決定論的 metadata JSON
- dict/set iteration order のリーク無し

### 6. SC#3 診断が単独では弱い
rare-category テストは有用だが不十分。意図的リーク実装がテスト fail すること、高基数 `_code` 列、unseen category、missing sentinel、train/eval/predict の全経路を含むべき。

### 7. Live DB 利用境界の精密化必要
SC#1 は stamped Parquet のみ・live DB 禁止。計画は label と market baselines で DB を使う。Parquet snapshot が label を欠くなら受容されうるが「Parquet-only 学習」を弱める。理想的には学習 snapshot が stamped label snapshot に join 済みであるべきであり、live `label.fukusho_label` ではない。

### 8. Early Stopping Eval Set 契約が不完全
計画は eval set が calib/test と disjoint であることを要求するが、全 helper 経路で日付について calib より厳密に前であることを要求しない。`max(eval.race_date) <= max(train_core.race_date) < min(calib.race_date)` を追加。

### 9. Phase 4 vs Phase 6 境界が曖昧
evaluator は受入的な `sum(p)` 検査と「Calibration 重視」選定素材を含む。reporting としては妥当だが Phase 4 が暗黙に最終確率品質ゲートになってはならない。

---

## Goal-Backward Verdict（ゴールバックワード判定）

計画を実行すれば文書上で稼働する Phase 4 pipeline（依存・schema・model 訓練・予測永続化・baseline 比較・検証 artifact）は概ね生成されるだろう。

しかし**書かれたままでは Core Value を完全には保証しない**。

残存 gap:
- CatBoost の高基数 `_code` 列の categorical 扱いが未解決
- sort/split 後の予測 row alignment が未証明
- label が stamped snapshot 一部でなければ「Parquet-only 学習」が live DB label join で弱まる
- SC#3 診断は false-pass しうる、全 categorical 経路の target/mean encoding 非存在を直接証明しない
- thread count/timestamp/category 順序/metadata 非決定論で bit-identical 再現性が fail しうる
- SC#2 が比較表を生成しても「model が付加価値を持つ」を保証しない

SC mapping:
- **SC#1:** 概ね cover、ただし live label join で明示的に許可/stamped されない限り Parquet-only が損なわれる
- **SC#2:** 表生成は cover、baselines 上の付加価値は保証されない
- **SC#3:** 部分 cover、CatBoost `_code` 扱いと診断強度が不十分
- **SC#4:** 構造的計画済み、ただし bit-identical 制御の強化が必要

## Risk Assessment

**総合リスク: HIGH**

計画は綿密で脅威モデルも正しいが、Phase 4 は「ほぼ正しい」では足りないほどリーク感受性が高い。最も高いリスクは CatBoost categorical semantics・row-order alignment・全テーブル prediction 置換・live DB label 依存・SC#3/SC#2 達成の過大請求。これらの契約を実装前に引き締めれば、文書上「完了」しながらリークフリー再現可能 `p_fukusho_hit` 不変量を違反するフェーズになる確率を大幅に下げられる。

---

## Consensus Summary

※本 cycle は Codex 単独レビューのため「複数レビュアーの合意」は成立しない。以下は Codex 単独レビューの主要合致点を「reviewer 間で再発すれば最優先になる懸念」として整理したもの（将来 cycle で Claude/Gemini が加われば合意抽出対象）。

### Agreed Strengths（単独レビュー内で複数 PLAN に共通する強み）
- 依存ライブラリ固定・prediction schema 早期定義・RED stub による検証契約の固定（04-01）
- `fit_prefit_calibrator` の再実装禁止・`raise ValueError` guard 要求（04-02/04-03）
- staging-swap idempotent load の既存パターン再利用・provenance 列検証（04-04）
- SC#3/SC#4 を構造的ブロッカーとする最終ゲート設計（04-06）
- LightGBM native categorical と CatBoost `has_time=True` の明示的要求（04-03）

### Agreed Concerns（最優先 — 複数の PLAN / クロスプランにまたがる HIGH）
1. **CatBoost 高基数 `_code` 列の categorical 扱いが未解決**（04-03 HIGH × Cross-Plan #2）— MODL-03 の核心違反リスク
2. **row alignment が全 pipeline で未保証**（04-05 HIGH × Cross-Plan #4 × 04-02 HIGH）— sort/split/merge 後に予測が誤馬へ書き込まれ GREEN のままになる silent failure
3. **prediction staging-swap のテーブル全体置換が model_type 別実行で前者を削除**（04-04 HIGH × 04-05 MEDIUM × Cross-Plan #3）— Phase 5 永続化契約の破綻
4. **model_version 形式が D-10 例と矛盾**（04-04 HIGH × Cross-Plan #1）— provenance 一意性の崩壊
5. **artifact save が CalibratedClassifierCV を native 形式で保存しようとして失敗**（04-05 HIGH × 04-02 MEDIUM）— artifact 聖域の崩壊
6. **SC#3 leak diagnostic が false-pass しうる・高基数 `_code` 列を検証しない**（04-03 HIGH × 04-06 HIGH × Cross-Plan #6）— MODL-03 構造証明の検証力不足
7. **`as_of_datetime = now()` とデフォルトスレッドが bit-identical を損なう**（04-04 MEDIUM × 04-05 HIGH × Cross-Plan #5）— SC#4 聖域リスク
8. **ROADMAP が SC#2「付加価値あり」を比較表存在だけで達成扱いしうる**（04-06 HIGH）— Phase 4 ゴールの過大請求
9. **`prepare_model_matrix(df)` 契約混乱と `assert_matrix_columns_registered` 誤適用**（04-02 HIGH ×2）— fake-green リスク

### Divergent Views
※単独レビューのため該当なし。Claude/Gemini が追加されれば、SC#3 診断の強度評価や CatBoost `_code` 文字列化の推奨強さについて分岐が生じうる領域。

---

<!-- ============================================================ -->
<!-- CYCLE 2 — 改訂 PLAN に対する再レビュー（commit 2455424 以降） -->
<!-- Cycle 1 セクションは上記に監査証跡として保全 -->
<!-- ============================================================ -->

## Cycle 2 — Codex 再レビュー（改訂 6 PLAN 対する収束判定）

**実施日**: 2026-06-20
**対象 commit**: 2455424 "revise plans to resolve 19 HIGH + actionable review findings"
**レビュア**: Codex gpt-5.5 / codex-cli 0.139.0（Cycle 1 と同一モデル・独立セッション）
**判定**: **大幅改善・19 HIGH 中 14 が FULLY RESOLVED・4 が PARTIALLY・1 が UNRESOLVED（実質回帰）。新規 HIGH 1 件・新規 actionable 4 件。**

### Cycle 2 の方法

Cycle 1 で指摘した 19 HIGH と actionable MEDIUM/LOW を改訂 6 PLAN の task/action/acceptance_criteria/verify/must_haves/threat_model/artifact 内容に照合し、(a) 単に言及されたか、(b) `/gsd-execute-phase` が実装する実行可能契約に変換されたか、を判定。加えて対抗的に新規懸念を走査（`align_predictions` の reindex NaN・staging `INSERT SELECT *` の列順序依存・BL-5 thread pinning・model_version 文書矛盾）。

---

### Cycle 1 HIGH 19件の収束判定（PLAN 単位）

#### 04-01（基盤）

| Cycle 1 HIGH | 判定 | 根拠 |
|---|---|---|
| HIGH#1 DDL PK 不足 | **FULLY RESOLVED** | `PREDICTION_TABLE_DDL` PK が `(model_type, model_version, feature_snapshot_id, as_of_datetime, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)` の11カラム・3 CHECK 制約付き・Task 1 action / acceptance / threat_model T-04-03 / Artifacts 全てに固定 |
| (actionable) schema 修飾 / RED stub 件数 / uv lock | **RESOLVED** | prohibition で `search_path 暗黙解決ではなく schema 修飾 SQL のみ`・RED stub 20件厳密・`uv lock --check` acceptance 追加 |

#### 04-02（data + calibrator + artifact）

| Cycle 1 HIGH | 判定 | 根拠 |
|---|---|---|
| HIGH#2 prepare_model_matrix 契約混乱 | **FULLY RESOLVED** | `load_feature_matrix / load_labels / build_training_frame / make_X_y / prepare_model_matrix` に5関数分離・合成 label DataFrame injection で DB 依存をテストから排除（fake-green 防止・T-04-12b） |
| HIGH#3 allowlist 誤適用 | **FULLY RESOLVED** | `FEATURE_COLUMNS` を registry 由来の明示的 allowlist とし metadata/raw-ID/label 除外・`X.columns == FEATURE_COLUMNS` 完全一致 assert（T-04-12c） |
| HIGH#4 race ID 不安定 | **FULLY RESOLVED** | 正準 `race_key=(year,jyocd,kaiji,nichiji,racenum)` ビルダ・race_nkey 静かフォールバック廃止 |
| HIGH#15（04-02 側） artifact wrapper 保存曖昧 | **PARTIALLY RESOLVED** | base native + `calibrator.joblib` 分離保存は plan 化・ただし `load_native_artifact` は base ネイティブファイルから真正再構築するのでなく `calibrator.joblib` をそのまま読み・base ファイルは型整合 assert のみに使用（機能的 roundtrip test は保たれるが「native base から再構築」の要求は弱い） |

#### 04-03（trainer + baseline）

| Cycle 1 HIGH | 判定 | 根拠 |
|---|---|---|
| HIGH#5 CatBoost `_code` 数値扱い | **FULLY RESOLVED** | `HIGH_CARD_CODE_COLS` を `astype(str)` で文字列化し `cat_features` に含めることが must_have / Task 1 action / acceptance / threat T-04-13b / test に固定 |
| HIGH#6 rare-category false-pass | **FULLY RESOLVED** | `_build_intentional_leak_control` で target encoding 風リーク注入時に予測が 0.9 超える（DEMONSTRABLY fail）ことを別 assert で実証 |
| HIGH#7 高基数 `_code` 未検証 | **FULLY RESOLVED** | `jockey_id_code` の train-only/test-unseen 希少 ID で予測が global mean に縮むことを test に追加 |
| HIGH#8 CatBoost Pool sort 強制不能 | **PARTIALLY RESOLVED** | `(Pool, sorted_index)` 返却 + `align_predictions` 復元は plan 化・ただし `align_predictions` が厳密置換を検証せず reindex の silent NaN を検出しない（新規 actionable 参照） |

#### 04-04（predict + prediction_load + evaluator）

| Cycle 1 HIGH | 判定 | 根拠 |
|---|---|---|
| HIGH#9 model_version 形式 | **PARTIALLY RESOLVED** | action/acceptance/test は `20260620-1a-postreview-v2-lgb-v1` で正しい・しかし behavior ブロックと `read_first` に古い `20260620-1a-lgb-v1` 例が残存（文書矛盾・新規 actionable） |
| HIGH#10 staging-swap 全テーブル破壊 | **PARTIALLY RESOLVED** | `DELETE WHERE model_type+model_version` で scope 化・`test_model_version_scoped_swap_preserves_other_models` で lightgbm 書込後 catboost 書込でも lightgbm 残ることを実証・ただし Step 9 が `INSERT ... SELECT * FROM staging` で列順序依存（新規 actionable） |
| HIGH#11 index/comment/GRANT 破壊 | **FULLY RESOLVED** | 本テーブルを DROP/RENAME せず staging のみ破壊・`LIKE ... INCLUDING ALL` で制約保全 |

#### 04-05（orchestrator + run_train_predict）

| Cycle 1 HIGH | 判定 | 根拠 |
|---|---|---|
| HIGH#12 train_and_predict が calibrator.py 所属 | **FULLY RESOLVED** | `src/model/orchestrator.py` 新設・`grep -c 'def train_and_predict' src/model/calibrator.py == 0` acceptance・`test_no_circular_import` |
| HIGH#13 split 前 prepare / metadata 不保持 | **PARTIALLY RESOLVED** | index 付き modeling frame を全段で運び index equality assert を入れた・ただし `train_and_predict(feature_df, ...)` が `readonly_cur/label_df` を取らず run script 側で label join 済み frame を渡す契約がやや暗黙 |
| **HIGH#14 CatBoost sort 済み予測が元順序に戻らない** | **UNRESOLVED（実質回帰）** | orchestrator は `align_predictions` で整列済み `pred_proba` を作るが・直後に `predict_p_fukusho(calib_result.calibrated, X_test, ...)` を呼び `predict_p_fukusho` 内部で `calibrated_estimator.predict_proba(X)[:,1]` を**再計算**するため aligned 予測は捨てられる。`predict_p_fukusho` のシグネチャが estimator のみ受け取り `pred_proba` を受け取らないため CatBoost 予測整列が最終 `pred_df` に反映されない経路になる。Cycle 1 HIGH#14 の核心（silent wrong-horse prediction）が plan 上で未解決 |
| HIGH#15（04-05 側） artifact save | **PARTIALLY RESOLVED** | `save_native_artifact` 分離保存を消費する契約は明示・04-02 側 loader 設計の弱さ（上記）と連動 |
| HIGH#16 reproduce smoke 非 bit-identical | **FULLY RESOLVED** | `num_threads=1/thread_count=1` + 固定 `as_of_datetime` + `np.array_equal` + `--check-reproduce` + `_assert_deterministic` が acceptance に固定 |

#### 04-06（最終検証 + ROADMAP）

| Cycle 1 HIGH | 判定 | 根拠 |
|---|---|---|
| HIGH#17 SC#3 を live-data 証明と過大請求 | **FULLY RESOLVED** | 「対抗的構造診断」「合成データ」「live-data 証明と称さない」が must_have / prohibition / ROADMAP 更新契約に固定 |
| HIGH#18 KEIBA_SKIP_DB_TESTS green-by-skip | **FULLY RESOLVED** | `unset KEIBA_SKIP_DB_TESTS && uv run pytest`・critical skipped count == 0・`final_gate_run_with_skip_unset: true` acceptance |
| HIGH#19 SC#2 比較表だけで付加価値扱い | **FULLY RESOLVED** | 「比較表生成」と「主モデルが BL を具体指標で上回るか」を分離・未達なら「AI 付加価値未証明」と注記 |

#### Cycle 1 actionable MEDIUM/LOW の収束

search_path 修飾 / RED stub 20件厳密 / uv lock --check / 厳密時系列 test_min<=test_max / SHA256 完全 hash+scope / LightGBM `_code` 非負 assert / BL-3 §14.2 注記 / BL-4/5 キャリブレーション注記 / as_of_datetime 制御 / sum(p) 診断的 / binning 契約固定 / .md+.json 分離 / --snapshot-id 実パス解決 / <120s 参考指標化 / validation 実行証拠格納 — **いずれも RESOLVED**（task/action/acceptance に組み込み済み）。

---

### 新規懸念（Cycle 2 で発見）

#### NEW HIGH-1: CatBoost 予測整列が最終 prediction DataFrame に反映されない経路（HIGH#14 の実質回帰）

**深刻度: HIGH**（核心価値「馬ごとのリークなし `p_fukusho_hit`」に直結・silent wrong-horse prediction 再発リスク）

**問題**: 04-05 orchestrator の action step 2 は CatBoost 予測を次のように処理する:
1. `pred_proba_sorted = calib_result.calibrated.predict_proba(X_test_cb_pool)[:,1]`（sort 済み Pool）
2. `pred_proba = align_predictions(...)` で元順序復元 ← **この結果は使われない**
3. `pred_df_test = predict_p_fukusho(calib_result.calibrated, X_test, ...)` ← `predict_p_fukusho` 内部で `calibrated_estimator.predict_proba(X)[:,1]` を**再計算**

`predict_p_fukusho`（04-04 Task 1）のシグネチャは `predict_p_fukusho(calibrated_estimator, X, ...)` であり・aligned 予測値を受け取らない。そのため orchestrator が算出した aligned `pred_proba` は捨てられ・`predict_p_fukusho` が再度予測する。CatBoost の `predict_proba(X)` が内部で Pool 再構築時に再 sort すれば予測順序が元の `X_test.index` と一致せず・silent wrong-horse prediction になる。Cycle 1 HIGH#14 の核心が再発。

**必要な PLAN 修正（Cycle 3 で再計画）**:
- `predict_p_fukusho` に `pred_proba` 引数を追加（`predict_p_fukusho(*, calibrated_estimator=None, X=None, pred_proba=None, ...)` いずれかを必須化）・orchestrator は aligned `pred_proba` を渡す
- または CatBoost 専用 predict helper を新設し `sort → predict_proba → align_predictions → provenance DataFrame 構築` を一貫担当
- acceptance に「CatBoost の場合 `predict_p_fukusho` に渡る予測値が `align_predictions` 出力と同一であること」を assert

#### NEW-2: `align_predictions` が厳密置換を検証しない（actionable MEDIUM）

**深刻度: MEDIUM**（HIGH-1 が解消されれば影響縮小・だが安価な安全網として必須）

**問題**: 04-03 Task 1 action step 7 の `align_predictions` は `pandas.Series(pred_series.values, index=sorted_index).reindex(original_index)` を使う。`sorted_index` が `original_index` の厳密な置換でなく部分集合の場合・`reindex` は欠落 index に **silent NaN** を生成し・戻り index は `original_index` と一致するため現状の `index.equals` assert は通ってしまう。CatBoost Pool が（全 `__MISSING__` センチネル等で）行を黙示に落とした場合・予測値 NaN が wrong-horse prediction として伝播しうる。

**必要な PLAN 修正**: `align_predictions` の acceptance に次を追加: `sorted_index.is_unique` / `original_index.is_unique` / `set(sorted_index) == set(original_index)` / `len(sorted_index) == len(original_index)` / `assert not aligned.isna().any()` を RuntimeError guard 化。

#### NEW-3: staging Step 9 の `INSERT ... SELECT * FROM staging` が列順序依存（actionable MEDIUM）

**深刻度: MEDIUM**（`LIKE ... INCLUDING ALL` が順序保存するため現状は安全だが将来 DDL 変更で脆弱）

**問題**: 04-04 Task 2 action Step 9 は `INSERT INTO prediction.fukusho_prediction SELECT * FROM prediction.fukusho_prediction_staging`。列リストを明示しないため・将来 DDL に列追加・順序変更が入ると誤列挿入または runtime failure になる。Step 6 は明示的 `cols_sql` を使うため一貫性もない。

**必要な PLAN 修正**: Step 9 を `INSERT INTO prediction.fukusho_prediction (<PREDICTION_COLUMNS csv>) SELECT <PREDICTION_COLUMNS csv> FROM prediction.fukusho_prediction_staging` に固定。

#### NEW-4: model_version 文書矛盾（actionable MEDIUM/LOW）

**深刻度: MEDIUM/LOW**（test は正しい形式を固定するため実行時安全・だが実装者が古い例を採用する危険）

**問題**: 04-04 Task 1 behavior の `test_model_version_numbering` docstring と `read_first` に古い形式 `"20260620-1a-lgb-v1" / "20260620-1a-cb-v1"`（feature_snapshot_id の `-1a` 部分のみ使用）が残る。RESEARCH D-10 も同じ古い例。action/acceptance は `20260620-1a-postreview-v2-lgb-v1`（feature_snapshot_id 全体を prefix）で正しいが・実装者が behavior の古い例を権威的に扱うと矛盾する仕様を固定しうる。

**必要な PLAN 修正**: 04-04 behavior ブロックと `read_first` と RESEARCH D-10 例を `20260620-1a-postreview-v2-lgb-v1` に統一。

#### NEW-5: artifact loader が native base から真正再構築しない（actionable MEDIUM）

**深刻度: MEDIUM**（機能的 roundtrip は保たれる・だし Cycle 1 HIGH#15 の「base+calibrator から再構築」要求は部分的）

**問題**: 04-02 Task 2 action step 5 の `load_native_artifact` は `calibrator.joblib` を読み込むのみ・`calibrator.estimator` の型が base_model_type と整合することを assert するが・native base ファイル（`lgb_model.txt`/`cb_model.cbm`）から CalibratedClassifierCV を**真正再構築**しない。そのため native base ファイルは検証用確証オブジェクトになり・joblib 依存度が高い（joblib は Python マイナーバージョン間で非互換になりうる）。

**必要な PLAN 修正**: `load_native_artifact` が (a) native base ファイルから base estimator を読み込み (b) `calibrator.joblib` から calibrators を読み込み (c) base + calibrators から CalibratedClassifierCV を再構築する契約に強化・または joblib 依存を減らす方向を docstring で明示。

---

### Cross-Plan 統合判定

**Cycle 1 HIGH 19件の総合**:
- **FULLY RESOLVED**: 14件（#1/#2/#3/#4/#5/#6/#7/#11/#12/#16/#17/#18/#19 + HIGH#15 の機能面）
- **PARTIALLY RESOLVED**: 4件（#8/#9/#10/#13）
- **UNRESOLVED**: 1件（#14 — NEW HIGH-1 として再発）

**新規**: HIGH 1件（NEW HIGH-1）+ actionable MEDIUM 4件（NEW-2..5）

**最優先（複数 PLAN / クロスプランにまたがる）**:
1. **NEW HIGH-1（HIGH#14 回帰）**: CatBoost 予測整列が `predict_p_fukusho` の再予測で捨てられる・核心価値違反・Cycle 3 で必須修正
2. **NEW-2**: `align_predictions` の reindex silent NaN guard 欠如・NEW HIGH-1 と連動
3. **NEW-3**: staging `INSERT SELECT *` の列順序依存・provenance 聖域の脆弱性
4. **NEW-4**: model_version 文書矛盾・実装者誘導リスク
5. **NEW-5**: artifact loader の native base 真正再構築欠如・HIGH#15 部分解決の残渣

### Goal-Backward Verdict

改訂 PLAN は Cycle 1 の大半を実行可能な task/test/acceptance/threat_model に落とし込み・特に DDL 11カラム PK + CHECK・CatBoost `_code` cat_features 文字列化・SC#3 過大請求防止・SC#4 固定 thread/as_of_datetime・final gate skip 禁止・SC#2 2要素分離は大きく改善された。これらは Cycle 1 では「文書で触れるのみ」だったものが `/gsd-execute-phase` が実装する契約に変換された点で評価できる。

しかし**核心価値である「馬ごとのリークなし `p_fukusho_hit`」に直結する CatBoost 予測行整列が、orchestrator と `predict_p_fukusho` の API 接続ミスで実質未解決（NEW HIGH-1）**。現状のままでは `align_predictions` を実装してもその出力が最終 prediction DataFrame に使われない経路になり・Cycle 1 HIGH#14 の silent wrong-horse prediction が再発しうる。

結論: **Cycle 2 は大幅改善だが・Phase 4 実装に進める前に NEW HIGH-1（CatBoost 予測整列の API 接続）を PLAN 修正すべき。** 加えて NEW-2..5（actionable MEDIUM）も実装前に対処すれば Cycle 1 HIGH は実質収束に極めて近づく。

### Risk Assessment

**総合リスク: MEDIUM**（Cycle 1 の HIGH から低下・ただし NEW HIGH-1 が残るため LOW ではない）

Cycle 1 の 19 HIGH のうち 14 が FULLY RESOLVED となり・リーク防止不変量の大部分（DDL・categorical・calibration・reproduce・gate）は実行可能契約に変換された。残る NEW HIGH-1 は局所的（CatBoost 予測 API 接続）で修正コストは小さい（`predict_p_fukusho` に `pred_proba` 引数を追加する程度）が・核心価値に直結するため Cycle 3 で必須。NEW-2..5 は実装前に対処推奨だが Phase 4 完了をブロックするほどではない。

---

## Cycle 3 — Codex 最終収束レビュー（第2再計画 commit 7214287 に対する収束判定）

本レビューは Codex（gpt-5.5 / codex-cli 0.139.0・Cycle 1/2 と同一モデル・独立セッション）による **Cycle 3（最終収束サイクル・max-cycles=3）** レビューです。第2再計画（commit 7214287 "plan revision Cycle 3 (NEW HIGH-1 + NEW-2..5 + residual #13)"）が Cycle 2 の残存6件をエンドツーエンドで解消したかを判定する最終関門として実施しました。レビュアは cycle-2 指摘の収束判定（任務 A）・cycle-1 解決 HIGH の回帰走査（任務 B）・新規懸念の対抗走査（任務 C）を実行し、レビュアの事前検証（grep/excerpt ベース）とクロスチェックして一致を確認済みです。

**対象 commit**: 7214287 "plan revision Cycle 3 (NEW HIGH-1 + NEW-2..5 + residual #13)"
**レビュア**: Codex gpt-5.5 / codex-cli 0.139.0（Cycle 1/2 と同一モデル・独立セッション）
**判定**: **CONVERGED — Cycle 2 の6件中5件 FULLY RESOLVED・1件 PARTIALLY（文書残渣のみ）・残存 HIGH 0件・cycle-1 回帰なし・新規 HIGH なし。**

### Cycle 3 の方法

第2再計画が更新したファイル（04-02/04-03/04-04/04-05-PLAN + 04-RESEARCH）と、cycle-2 指摘の実行可能契約化（task/action/acceptance/verify/threat_model/test）を照合。加えて cycle-1 の 14件 FULLY-RESOLVED HIGH（特に DDL 11カラム PK・CatBoost `_code` cat_features・SC#3 DEMONSTRABLY fail・thread pinning）が第2再計画で回帰していないか走査し、対抗的に新規懸念を検索。レビュアは codex 出力と独立 grep 検証の両方で一致を確認。

### 任務 A — Cycle 2 の6件の収束判定

| Cycle 2 指摘 | 判定 | 根拠（PLAN の箇所） |
|---|---|---|
| **NEW HIGH-1**（CatBoost pred_proba API・HIGH#14 回帰） | **FULLY RESOLVED** | 04-04 Task 1 が `predict_p_fukusho(..., pred_proba=None)` を signature に明示。「渡された場合はそれを直接使用し再予測しない」「pd.Series の場合は `pred_proba.index.equals(X.index)` を assert・違反は RuntimeError」「np.ndarray の場合は `pd.Series(pred_proba, index=X.index)` に正規化」を契約化。test `test_predict_uses_injected_pred_proba` が「np.array_equal（注入値が使われ再予測されない）」「index 不一致は RuntimeError」を両方実証。04-05 orchestrator の call site（action step 6）が `pred_proba=pred_proba` を明示的に渡す・`test_catboost_pred_proba_injection` が「最終 pred_df の p_fukusho_hit 列が align_predictions 復元した pred_proba と np.array_equal」を assert・入力シャッフルでも index 復元を検証。threat `T-04-25c`（04-04）と `T-04-31b`（04-05）が連動で mitigate。verify acceptance に `grep 'predict_p_fukusho' src/model/orchestrator.py` に `pred_proba=` 含有確認。**signature → call site → test → threat → verify grep までエンドツーエンドで閉塞済み・Cycle 1 HIGH#14 の silent wrong-horse prediction は構造的に不可能。** |
| **NEW-2**（align_predictions reindex silent NaN guard） | **FULLY RESOLVED** | 04-03 Task 1 action step 7 が `align_predictions(pred_series, sorted_index, original_index)` に5条件を RuntimeError guard として契約化: (a) `sorted_index.is_unique` (b) `original_index.is_unique` (c) `set(sorted_index) == set(original_index)` (d) `len(sorted_index) == len(original_index)` (e) `not aligned.isna().any()`。test `test_catboost_predict_preserves_row_order` が「部分集合 index（1行削除）」「重複 index（1行複製）」「予測長不一致」で `pytest.raises(RuntimeError)` を要求・reindex silent NaN/dup/drop の fail-loud を実証。threat `T-04-15c` に登録。verify に `grep -c 'is_unique' src/model/trainer.py >= 1`。NEW HIGH-1 の安全網としても機能。 |
| **NEW-3**（staging INSERT SELECT * 列順序依存） | **FULLY RESOLVED** | 04-04 Task 2 action Step 9 が `INSERT INTO prediction.fukusho_prediction ({cols_sql}) SELECT {cols_sql} FROM prediction.fukusho_prediction_staging` を明示・`cols_sql` は Step 6 と同一の `", ".join(PREDICTION_COLUMNS)` 文字列・psycopg.sql.SQL で safe composition。verify acceptance に `grep -c 'SELECT \* FROM prediction.fukusho_prediction_staging' src/db/prediction_load.py == 0`・将来 DDL 変更で誤列挿入を防止。threat `T-04-21b` に登録。 |
| **NEW-4**（model_version 文書矛盾） | **PARTIALLY** | 04-04 behavior/read_first と RESEARCH D-10（行687-688）は `20260620-1a-postreview-v2-lgb-v1`/`-cb-v1` に統一済み（action/acceptance/test も同形式で正しい）。**ただし第2再計画が触れていない3ファイルに古い形式の残渣あり**: (1) 04-01-PLAN.md 行179 `test_model_version_numbering（D-10: 20260620-1a-lgb-v1 / 20260620-1a-cb-v1 形式）`・(2) 04-PATTERNS.md 行157 `例: 20260620-1a-lgb-v1`・(3) 04-CONTEXT.md 行50 `例: 20260620-1a-lgb-v1 / -cb-v1`。実装契約の中心（action/acceptance/test）は新形式なので実行時安全だが・実装者が古い stub/patterns/context を参照する余地が残る。**LOW actionable**（後述）。 |
| **NEW-5**（load_native_artifact 真正再構築） | **FULLY RESOLVED** | 04-02 Task 2 action step 5 が3ステップを契約化: (a) native base ファイル（lgb_model.txt/cb_model.cbm）から base estimator を読込（FileNotFoundError guard）(b) calibrator.joblib から calibrators を読込 (c) base + calibrators から CalibratedClassifierCV を真正再構築（`_calibrators`/`.calibrated_classifiers_` 注入）。acceptance に「native base ファイルから真正読込し base+calibrators から真正再構築」・docstring に「予測の中心は native base から復元した estimator・joblib は calibrators 純粋数値の運び屋」明記。test `test_artifact_save_load_roundtrip` が「純粋 joblib 依存でないこと」を実証。threat `T-04-11` 拡張済み。**ただし再構築が sklearn 1.9 私有/準私有構造（`_calibrators`/`calibrated_classifiers_`）に依存する実装難度は残る → 別途 MEDIUM actionable（後述）。** |
| **residual #13**（label join 位置が暗黙） | **FULLY RESOLVED** | 04-05 `train_and_predict(feature_df, *, model_type, ...)` が `readonly_cur`/`label_df` 引数を持たず label-joined frame のみを受け取る。docstring に "feature_df must be the output of build_training_frame (label-joined). train_and_predict does NOT rejoin labels." 明記・入口で `assert "fukusho_target" in feature_df.columns`（違反は ValueError）。run script（action step 8）が `load_feature_matrix → load_labels → build_training_frame → train_and_predict(feature_df)` で label join を完結・run script 側でも `fukusho_target` 列存在を assert（二重防御）。verify acceptance に `grep -c 'load_labels\|readonly_cur' src/model/orchestrator.py == 0`。 |

### 任務 B — Cycle 1 回帰走査

**回帰なし。** 第2再計画が cycle-1 の 14件 FULLY-RESOLVED HIGH を保持:

- **HIGH#1 DDL**（04-01）: 11カラム PK（model_type/model_version/feature_snapshot_id/as_of_datetime + 7カラム RACE_KEY）+ 3 CHECK 制約（p_fukusho_hit ∈ [0,1] / model_type IN ('lightgbm','catboost','logreg') / calib_method IN ('isotonic','sigmoid')）を維持。T-04-03 threat も維持。
- **HIGH#5/#6/#7 CatBoost**（04-03）: `HIGH_CARD_CODE_COLS`（jockey_id_code/trainer_id_code/sire_id_code/bms_id_code/horse_id_code）を `astype(str)` で文字列化し cat_features に含めることを action step 4/test `test_catboost_has_time`/threat で維持。SC#3 leak diagnostic は「低基数 RARE_X + 高基数 _code train-only/test-unseen + `_build_intentional_leak_control` で DEMONSTRABLY fail」を維持。
- **HIGH#9 model_version**（04-04）: `make_model_version` が `{feature_snapshot_id}-{short}-v{N}`（例: 20260620-1a-postreview-v2-lgb-v1）・二重 suffix 防止の test を維持。
- **HIGH#16 thread pinning + as_of_datetime**（04-05）: `num_threads=1`（LightGBM）/ `thread_count=1`（CatBoost）+ 固定 `as_of_datetime`（FIXED_REPRODUCE_TS）+ `np.array_equal` の bit-identical を `_assert_deterministic`/`test_reproduce_bit_identical` で維持。

**軽微な文書ドリフト（実行時影響なし・回帰ではない）**: 04-04 read_first に `schema.py（PLAN 01: PREDICTION_TABLE_DDL・9カラム PK・列名・型）` という記述があるが・同 PLAN 本文・acceptance は 11カラム PK を参照しており実装契約としての回帰ではない（実装者は acceptance/本文が権威）。

### 任務 C — 新規懸念（対抗走査）

**新規 HIGH: なし。** 予測整列・label join・staging INSERT の核心リスクは全て収束。

**新規 MEDIUM**:
- **NEW-M1: artifact 復元の sklearn 内部 API 依存**。04-02 action step 5 (c) が `_calibrators` 属性への注入・又は `.calibrated_classifiers_` への再 bind を許容。これらは sklearn 1.9 の私有/準私有構造で・マイナーバージョン変更で破壊されうる。契約自体（3ステップ再構築・roundtrip test）は十分だが・実装時には「保存形式を calibrators 数値 payload + 公開 predict wrapper に寄せる」か・対象 sklearn バージョン（1.9.0 固定）下で roundtrip test を強くする必要がある。→ **actionable MEDIUM**（後述）。

**新規 LOW**:
- **NEW-L1: `calibrator.joblib を一時退避しても native base から再構築可能` の test 記述が物理的に不可能**。04-02 test `test_artifact_save_load_roundtrip` の「calibrator.joblib を一時退避しても native base から再構築可能・又は docstring に fallback 手順明記」は曖昧。calibrator 数値（isotonic 回帰の閾値/sigmoid パラメータ）なしでは calibrated probability は復元できず・native base 単独では未キャリブレーション予測しか出せない。fallback は「calibrator 数値が別途保存されている場合の手動復元」に限定して書くべき。→ **actionable LOW**。
- **NEW-L2: RESEARCH D-12 `calib_method='none'` と 04-01 DDL CHECK の不整合**。RESEARCH 行718 の comment は `'isotonic' / 'sigmoid' / 'none'` だが・04-01 DDL CHECK（行114）は `calib_method IN ('isotonic','sigmoid')` のみ。Phase 4 の LightGBM/CatBoost は両方とも必ずキャリブレーションする（`calibrate_model` が isotonic/sigmoid を強制）ので実行時影響なし・だが将来 baseline（未キャリブレーション）を prediction テーブルに入れる場合は DDL CHECK 又は RESEARCH のどちらかに統一が必要。→ **actionable LOW**。

### 残存 HIGH 懸念（Cycle 3 終了時点）

**なし。** Cycle 2 の核心だった CatBoost aligned `pred_proba` の最終 DataFrame 伝播（NEW HIGH-1）は signature → orchestrator call site → unit/orchestrator test → threat_model → grep acceptance まで完全に閉じた。残る問題は文書残渣（NEW-4 PARTIALLY・実行時安全）と artifact 復元の実装難度（NEW-M1）のみで・リークのない馬ごとの `p_fukusho_hit` と race_id 時系列バックテストという Phase 4 の核心を止める HIGH は存在しない。

### 残存 actionable MEDIUM/LOW 懸念

- **NEW-M1 (MEDIUM)**: artifact 復元（`load_native_artifact` step c）が sklearn 1.9 私有構造（`_calibrators`/`calibrated_classifiers_`）に依存する実装難度。04-02 PLAN.md の docstring/test に「保存形式を calibrators 数値 payload（isotonic 閾値/sigmoid 係数）+ 公開 predict wrapper に寄せる方向」を明示するか・`requires-python`/pyproject.toml で sklearn==1.9.0 を pin し roundtrip test を強化する方向を追記することが望ましい。execute-phase には見えないので PLAN に組み込むか明示的に defer が必要。
- **NEW-4 残渣 (LOW)**: 04-01-PLAN.md 行179・04-PATTERNS.md 行157・04-CONTEXT.md 行50 の古い model_version 形式（`20260620-1a-lgb-v1`/`-cb-v1`）を `20260620-1a-postreview-v2-lgb-v1`/`-cb-v1` に統一すること。実装者が古い stub/patterns/context を権威的に参照するリスクを排除。
- **NEW-L1 (LOW)**: 04-02 test `test_artifact_save_load_roundtrip` の「calibrator.joblib 一時退避で再構築可能」記述を「calibrator 数値が別途保存されている場合の手動復元」に限定して書き直すこと。物理的に不可能な fallback を契約に残さない。
- **NEW-L2 (LOW)**: RESEARCH D-12 行718 の `calib_method='none'` と 04-01 DDL CHECK（`('isotonic','sigmoid')`）のどちらかに統一すること。Phase 4 実行時影響なし・将来 baseline 拡張時の不整合防止。

### Goal-Backward Verdict

Cycle 2 で唯一残存した HIGH（CatBoost aligned `pred_proba` の最終 DataFrame 伝播・Cycle 1 HIGH#14 回帰）は・第2再計画で signature（`predict_p_fukusho` の `pred_proba` 引数）→ orchestrator call site（`pred_proba=pred_proba` 明示渡し）→ unit test（`test_predict_uses_injected_pred_proba`・np.array_equal + RuntimeError）→ orchestrator test（`test_catboost_pred_proba_injection`・シャッフル入力でも index 復元）→ threat_model（T-04-25c/T-04-31b 連動）→ verify acceptance（grep で `pred_proba=` 含有確認）までエンドツーエンドで閉じた。NEW-2/3/5 + residual #13 も実行可能契約に変換され・cycle-1 の 14件 FULLY-RESOLVED HIGH は回帰なく保持された。

残る問題は (a) NEW-4 の文書残渣（04-01 stub・04-PATTERNS・04-CONTEXT に古い model_version 形式・実行時安全）・(b) NEW-M1 の artifact 復元 sklearn 内部 API 依存（実装難度・契約は十分）・(c) NEW-L1/L2 の文書レベル不整合（実行時影響なし）のみで・いずれも Phase 4 の核心（リークのない馬ごとの `p_fukusho_hit`・race_id 時系列バックテスト）を止めるものではない。

**結論: Cycle 3 は CONVERGED。Phase 4 実装（`/gsd-execute-phase`）に進める。** 上記 actionable MEDIUM 1件 + LOW 3件は実装時対処推奨だが Phase 4 完了をブロックしない。

### Risk Assessment

**総合リスク: LOW**（Cycle 2 の MEDIUM から低下）

Cycle 2 で唯一残存した HIGH（CatBoost 予測整列 API 接続・核心価値直結）が解消され・cycle-1 の 19 HIGH は事実上全て収束（14 FULLY + 5 は第2再計画で閉塞・回帰なし）。リーク防止不変量（DDL・categorical・calibration・reproduce・gate・行整列・label join 境界・staging INSERT）は全て実行可能契約に変換された。残る actionable は実装難度（artifact 復元の sklearn 内部 API）と文書レベル（model_version 残渣・fallback 記述・calib_method CHECK）のみで・execute-phase が実装時に詰まるものではない。Phase 4 は実装フェーズに移行可能。

---

## Current HIGH Concerns

なし。Cycle 1 の 19 HIGH（cycle-2 で 14 FULLY + NEW HIGH-1 残存）は Cycle 3 で事実上全て収束。Cycle 2 の NEW HIGH-1（CatBoost 予測整列 API 接続・Cycle 1 HIGH#14 silent wrong-horse prediction 回帰）は signature → call site → test → threat → verify grep までエンドツーエンドで閉塞済み。cycle-1 回帰なし・新規 HIGH なし。

## Current Actionable Non-HIGH Concerns

なし。Cycle 3 の4件（NEW-M1 MEDIUM・NEW-4 残渣 LOW・NEW-L1 LOW・NEW-L2 LOW）は Cycle 4 で全て PLAN/doc に組み込み済・actionable=0 達成。

### Cycle 4 — Cycle 3 actionable 4件の組み込み（自己収束）

**実施日**: 2026-06-20
**対象**: Cycle 3 の actionable MEDIUM 1件 + LOW 3件
**判定**: FULLY CONVERGED — actionable=0 達成

| Cycle 3 指摘 | 判定 | 組込先（PLAN/doc の箇所） |
|---|---|---|
| **NEW-M1 (MEDIUM)**: `load_native_artifact` step (c) の sklearn 1.9 私有 API 依存 | **RESOLVED** | 04-02 PLAN.md: behavior test に `np.allclose(rtol=1e-12, atol=1e-12)` で保存前後 predict_proba 一致 assert を追加・action step 5(c) に scikit-learn==1.9.0 pin を安定性保証とする方針（選択肢 b）を明記・acceptance・threat T-04-11・must_haves truths・Artifacts に全て反映。pin 破壊は roundtrip test の即時 RED で検出する契約に変換 |
| **NEW-4 残渣 (LOW)**: 3ファイルの古い model_version 形式 | **RESOLVED** | 04-01-PLAN.md 行179・04-PATTERNS.md 行157・04-CONTEXT.md 行50 を `20260620-1a-postreview-v2-lgb-v1` / `-cb-v1` の正準形式に統一 |
| **NEW-L1 (LOW)**: `calibrator.joblib 一時退避で再構築可能` が物理的不可能 | **RESOLVED** | 04-02 PLAN.md: behavior test 記述を「base + calibrator.joblib の両方が揃った状態での roundtrip」のみを契約とし calibrator.joblib 欠落時 FileNotFoundError を検証する方に書き直し・action step 5(c)/docstring・acceptance・threat T-04-11・must_haves・Artifacts に「native base 単独では不可」を明記 |
| **NEW-L2 (LOW)**: RESEARCH D-12 `calib_method='none'` と 04-01 DDL CHECK の不整合 | **RESOLVED** | 04-RESEARCH.md D-12 行718 の comment から `'none'` を除去・04-01 DDL CHECK `('isotonic','sigmoid')` と整合。Phase 4 は両モデル必ずキャリブレーションなので 'none' はスコープ外・将来未キャリブレーション baseline は別テーブル/別 model_type で扱う旨を comment に明記 |

**構造保全**: 5-wave / 6-plan 構造は維持・Cycle 1-3 で解決済の HIGH 19件 + NEW HIGH-1 + NEW-2/3/5 + residual #13 の全契約は回帰なし。MODL-01/02/03 の requirements カバレッジも維持。

### Goal-Backward Verdict (Cycle 4)

Cycle 3 の4件 actionable は全て PLAN/doc の実行可能契約（action・acceptance・test・threat・must_haves・Artifacts・docstring）に変換され・残る未解決懸念は存在しない（actionable=0）。Phase 4 はリークのない馬ごとの `p_fukusho_hit` と race_id 時系列バックテストという核心を止める懸念が存在せず・`/gsd-execute-phase` に進める。
