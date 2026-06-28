---
slug: label-newcomer-universe
status: resolved
goal: find_and_fix
trigger: |
  【バグ】label newcomer_syubetucd '12' 誤除外で is_model_eligible の universe 壊壊。
  label.fukusho_label の is_model_eligible で、JRA で最多の「1勝クラス/未勝利」層が
  不適格(newcomer)として脱落。2023 test で 47672馬中 eligible 22793(48%)のみ。
  モデル学習・予測・backtest の universe が壊れている（ユーザー報告・実データ証拠付き）。
created: 2026-06-28
updated: 2026-06-28
checkpoint_answers:
  A_label_version: "bump する (v1.0.0 → v1.1.0)"
  B_feature_snapshot: "再生成不要（data.py 検証済み・feature Parquet 不変）"
  C_phase11_12: "凍結維持・新 universe 分離（label_version v1.1.0 で管理）"
  D_regen_auth: "main が直接実行（agent は fix + unit test GREEN まで・DB 書込しない）"
---

# Debug Session: label newcomer_syubetucd '12' 誤除外で is_model_eligible の universe 壊壊

## Symptoms

### Expected behavior
`label.fukusho_label.is_model_eligible` が、JRA 通常出走馬の大部分（1勝クラス/未勝利を含む）を適格と判定すること。新馬戦（`class_name_normalized='新馬'`）のみが newcomer として不適格になること。モデル学習・予測・backtest の universe が JRA の現実的な出走馬層を覆盖すること。

### Actual behavior
`is_model_eligible` の newcomer 除外ロジックが `syubetucd in ['11','12']` で判定されているが、`code_tables.yaml` の `"12"="3歳新馬（平地）"` が**実データと矛盾**している。実データ（2023 `normalized.n_race`）では `syubetucd='12'` の 1039 レースのうち新馬は 45 のみ・残り 994 は「1勝クラス/未勝利」。結果、JRA で最多の「1勝クラス/未勝利」層が newcomer として不適格脱落し、2023 test で eligible 22793(48%) / ineligible 24879（うち newcomer 23383）と universe が壊れている。

### Error messages
明示的エラー無し（silent・universe 定義の正しさの問題）。検出は Spike 001 ablation の A0 ゲート調査で発覚。

### Timeline
- 2026-06-28: Spike 001 ablation（`reports/12-evaluation/ablation-spec.md`）の A0 ゲート調査で発覚。実データ検証（live-DB readonly・2023）で `syubetucd='12'` の大部分が新馬でないことを確認。

### Reproduction
live-DB readonly・2023 で確認済み（ユーザー報告）：
- `class_name_normalized='新馬'` の syubetucd 分布: `'11'=257`, `'12'=45`（新馬は syubetucd '11'/'12' 両方に散在・'11' が多数）
- `syubetucd='12'` の `class_name_normalized` サンプル: `['1勝クラス','1勝クラス','1勝クラス','未勝利','未勝利']`
- syubetucd 分布（2023 n_race）: `'12'=1039 '13'=979 '14'=666 '11'=645 '18'=71 '19'=56`
- `label.fukusho_label` 2023: eligible 22793 / ineligible 24879（newcomer 23383・obstacle 1460・cancel 36）
- `is_fukusho_sale_available`: 全 47672（発売 filter 無関係）

## Root Cause（ユーザー分析・実データ証拠付き・検証待ち）

3 箇所の連鎖:
1. `src/config/label_spec.yaml` L85-87: `newcomer_syubetucd=["11","12"]`（§7.3 新馬戦除外）
2. `src/config/code_tables.yaml` L29-30: `"12"="3歳新馬（平地）"` → **実データと矛盾**（実測=1勝クラス/未勝利）
3. `src/etl/fukusho_label.py` `compute_is_model_eligible`（L460-540・newcomer 判定 L485-494）: `syubetucd in ['11','12']` → newcomer 除外

根本原因は newcomer 判定基準が「`syubetucd`（レース種別コード）」ではなく「`class_name_normalized`（クラス名）」であるべきところ、`syubetucd` で代理判定していること。`syubetucd='12'` は新馬専用ではなく 1勝/未勝利を含む混在コード（`code_tables.yaml` の定義自体が不正確・CODE.md 不完全の別事例・memory `jra-van-babacd-trackcd-code-system` と同系列）。

## Fix 方針（ユーザー案・debugger が codebase を読んで具体化・検証）

1. `src/config/label_spec.yaml`: newcomer 判定を `syubetucd` でなく `class_name_normalized='新馬'` に変更（syubetucd '12' の新馬 45 も正確に含む）。`newcomer_syubetucd` 廃止（または `newcomer_class_name` 等に置換）。
2. `src/etl/fukusho_label.py` `compute_is_model_eligible`: `syubetucd in newcomer_set` → `class_name_normalized == '新馬'`。**要確認**: row に `class_name_normalized` が伝播しているか（必要なら SE/race SELECT・merge 追加）。
3. `src/config/code_tables.yaml`: `"12"` の定義を訂正（実測=1勝クラス/未勝利）。`'11'/'13'/'14'` も実測確認（`'11'`=新馬は正・`'13'/'14'` は1勝/2勝/OP 等の混在）。
4. `label.fukusho_label` 再生成（ETL・`run_label_etl` 等）。
5. snapshot 再生成は不要とユーザー判断（`feature_matrix` 不変・label-join 後の universe が `build_training_frame` で変わる）→ **要検証**: feature snapshot に `is_model_eligible` 由来の row filter が無いか・universe 変化が feature 側に波及しないか。

## Files to investigate / fix 対象
- `src/config/label_spec.yaml`（newcomer_syubetucd・L85-87）
- `src/config/code_tables.yaml`（syubetucd 定義・L29-30）
- `src/etl/fukusho_label.py`（`compute_is_model_eligible`・L460-540・newcomer 判定 L485-494・`class_name_normalized` 伝播経路）
- `src/model/data.py`（`filter_eligible`・`build_training_frame`・universe の具現化箇所）
- `tests/test_fukusho_label.py`（is_model_eligible 関連テスト・§17.3 label unit test）
- label 再生成スクリプト（`scripts/run_label_etl.py` 等の実在確認）

## Constraints（厳守・聖域）

### core value・リーク防止（最重要）
本 fix は newcomer 判定基準の変更（universe 定義）であり、リーク（look-ahead/PIT 違反）を導入しない。`class_name_normalized` は race 静的属性（出馬表確定時に既知・`feature_cutoff_datetime` 以前に確定）なので feature に使っても PIT 安全。ただし newcomer 判定に race 結果由来の情報を使わないこと（純粋に `class_name_normalized`/`syubetucd` の事前属性）。

### raw 不変（D-06）
raw テーブルに一切書込まない。label/config/test のみ。

### 再現性（§19.1）・label_version 扱い【要判断】
本 fix は `is_model_eligible` の universe を大きく変える（1勝/未勝利層が復帰）。これは**ラベル定義の意味論的変更**であり:
- 既存の全レポート（Phase 5-12・`reports/12-evaluation` binary 0.7314 等）は**古い universe** のまま。
- `label_version` を bump すべきか（既存レポートとの整合・model_version の再現性 stamp 取り扱い）。
- Phase 11/12 は凍結済み（memory `phase11-frozen-rerun-forbidden`）。label universe 変更が Phase 11/12 の再現性・guard にどう影響するか要確認。
- snapshot 再生成要否（ユーザー案5=不要・`feature_matrix` 不変）を feature 側コードで検証。

### 既存テスト GREEN 維持
- §17.3 label/PIT/split unit test 群。
- is_model_eligible 関連の既存テスト（newcomer 除外を syubetucd 前提で書いている場合は更新必要）。

### 日本語（CLAUDE.md 最優先）
コミットメッセージ・コメント・docstring は全て日本語。

## 検証（debugger が具体化）

1. live-DB readonly で実データ再確認（2023 に限らず全期間）:
   - `class_name_normalized='新馬'` の syubetucd 分布（'11'/'12' 両方に散在の確認）。
   - `syubetucd='12'`（および '11'/'13'/'14'/'18'/'19'）の `class_name_normalized` 混在状況。
   - 修正前後で 2023 の eligible/ineligible 数がどう変わるか（eligible 40000+ に増加見込み）。
2. `compute_is_model_eligible` に `class_name_normalized` が伝播するかのコード確認（不足なら merge 追加）。
3. feature snapshot に `is_model_eligible` 由来の row filter が無いか確認（snapshot 再生成不要の検証）。
4. KEIBA_SKIP_DB_TESTS=1 → DB 必須テストの段階的 GREEN。
5. live-DB で label 再生成（`run_label_etl` 等）・idempotent（2回同一 checksum）・raw 不変・eligible 数の正常化確認。

## 前提
- Spike 001 ablation（commit b79b2b6/54e98be）の A0 ゲート調査から発見。
- memory `jra-van-babacd-trackcd-code-system`: JRA-VAN コード体系の CODE.md 不完全事例（TrackCD/BabaCD）と同系列の「`syubetucd` 定義不正確」問題。
- 最近の label 修正: `race-date-null-racekey-fix`（commit ef63e65・race_key ゼロ埋め正規化）・`d8dc4c9`（HARAI 払戻列伝播・recovery_rate 正常化）。

## Current Focus

- phase: fix-application（continuation・main から委譲・4 checkpoint 回答済み確定）
- hypothesis: newcomer/maiden 判定基準を `syubetucd` から `class_name_normalized` に変更する fix を適用する。label_version を v1.0.0 → v1.1.0 に bump。feature snapshot は不変（再生成不要）。Phase 11/12 凍結 artefact は label 再生成で上書きされない（参照経路確認済み）。
- test: (1) label_spec.yaml: newcomer_syubetucd/maiden_syubetucd を class_name_normalized 基準に置換 + label_version v1.1.0 (2) fukusho_label.py: _RACE_META_SELECT_COLUMNS に class_name_normalized 追加 + compute_is_model_eligible で class_name_normalized 判定 + race_extra_cols 伝播 (3) code_tables.yaml: syubetucd 定義を実測に訂正 (4) test_fukusho_label.py: 既存3テスト更新 + 新規回帰テスト追加。
- expecting: unit test GREEN（KEIBA_SKIP_DB_TESTS=1）・ruff GREEN・新規回帰テストで 1勝/未勝利 eligible・新馬のみ newcomer・未勝利救済正確 を検証。
- next_action: fix を4ファイルに適用 → unit test 実行 → ruff check → debug session 更新 → main に FIX APPLIED で返す（label 再生成は main が実行）。
- phase11_12_reference_path_verified: |
    確認結果（fix 適用前・2026-06-28）:
    (1) label.fukusho_label テーブルは独立（label スキーマ）。label 再生成は同テーブルのみ更新。
    (2) prediction.fukusho_prediction テーブルは model_type+model_version+feature_snapshot_id+as_of_datetime スコープで独立（src/db/prediction_load.py:313）。is_model_eligible 列を持たない（src/db/schema.py:61-98 に is_model_eligible 無し・provenance + 予測値のみ）。label 再生成の影響を受けない。
    (3) reports/11-evaluation/, reports/12-evaluation/ の JSON/MD は Phase 11/12 評価スクリプト（run_phase11_evaluation.py / run_phase12_evaluation.py）が atomic write で生成した凍結ファイル。label 再生成（run_label_etl.py）だけではこれらのファイルは上書きされない。
    (4) run_phase11_evaluation.py:326,384,413 は label_version="v1.0" をハードコード（Phase 11 評価時の universe は v1.0 universe）。label 再生成で label.fukusho_label.is_model_eligible が変わっても・Phase 11/12 スクリプトを再実行しない限り reports/*.json は不変。
    (5) feature snapshot（snapshots/*.parquet）は is_model_eligible で row filter しない（src/model/data.py: load_feature_matrix は Parquet のみ・filter_eligible は label 側 row filter）。label 再生成で feature snapshot は不変。
    結論: label 再生成（main 実行）は label.fukusho_label テーブルのみ更新。prediction テーブル・reports/*.json・feature snapshot は全て不変。Phase 11/12 凍結維持の前提確認完了。
- fix_scope:
    file_1_label_spec_yaml:
      - "label_generation_version: v1.0.0 → v1.1.0"
      - "newcomer_syubetucd 廃止 → newcomer_class_name: ['新馬'] 追加"
      - "class_eligibility.maiden_syubetucd 廃止 → maiden_class_name: ['未勝利'] 追加"
      - "class_eligibility.maiden_ineligible_syubetucd 廃止 → newcomer_class_name と統合"
      - "_REQUIRED_SPEC_KEYS の newcomer_syubetucd → newcomer_class_name に更新"
    file_2_fukusho_label_py:
      - "_RACE_META_SELECT_COLUMNS に class_name_normalized 追加（race 静的属性・PIT 安全）"
      - "compute_is_model_eligible: syubetucd in newcomer_set → class_name_normalized in newcomer_class_name_set"
      - "compute_is_model_eligible: syubetucd in maiden_set → class_name_normalized in maiden_class_name_set"
      - "race_extra_cols に class_name_normalized 追加（race_date/syubetucd と同一伝播経路）"
      - "docstring 更新（適用順序の newcomer/maiden 基準を class_name_normalized に）"
    file_3_code_tables_yaml:
      - "syubetucd の定義を実測に訂正（'11'/'12'/'13'/'14' は混在コード・'18'/'19' は正）"
      - "note 追加: syubetucd は馬齢カテゴリ（2歳/3歳/古馬）でクラス（新馬/未勝利/1勝...）と直交・class_name_normalized がクラスの唯一の正しい指標"
    file_4_test_fukusho_label_py:
      - "_build_label_input_df に class_name_normalized パラメータ追加"
      - "test_is_model_eligible_newcomer_syubetucd → test_is_model_eligible_newcomer_class_name に改名・class_name_normalized='新馬' 基準に"
      - "test_is_model_eligible_maiden_syubetucd_included → test_is_model_eligible_maiden_class_name_included に改名・class_name_normalized='未勝利' 基準に"
      - "test_is_model_eligible_class_below_minimum: class_name_normalized 追加"
      - "新規回帰テスト: syubetucd='12' + class_name_normalized='1勝クラス' は eligible（誤除外回帰防止）"
      - "新規回帰テスト: syubetucd='12' + class_name_normalized='未勝利' は eligible（maiden 救済）"
- reasoning_checkpoint:
    hypothesis: "newcomer/maiden 判定を syubetucd から class_name_normalized に変更する。syubetucd は馬齢カテゴリ（2歳/3歳/古馬）でクラス（新馬/未勝利/1勝...）と直交する混在コード（実測: syubetucd='12' は未勝利9611/1勝1559/OP629/新馬599）。class_name_normalized がクラスの唯一の正しい指標（jyokencd5='701'→新馬/'703'→未勝利/'005'→1勝クラス）。class_name_normalized は race 静的属性（出馬表確定時に既知・PIT 安全）。"
    confirming_evidence:
      - "label_spec.yaml L85-87 で newcomer_syubetucd=['11','12']・fukusho_label.py L493 で syubetucd in ['11','12'] → newcomer 除外（agent 再読込で確認）"
      - "ユーザー実データ検証（live-DB readonly・全期間）: syubetucd='12' は未勝利9611/1勝1559/OP629/新馬599 races・新馬は最少。code_tables.yaml の '12'='3歳新馬' は全面矛盾。"
      - "修正後 eligible 予測（2023）: 42281 horses（現在 22793 から +19452）・newcomer_proposed=3931（class_name_normalized='新馬' のみ）"
      - "Phase 11/12 参照経路確認: label 再生成は label.fukusho_label のみ・prediction/reports/feature snapshot は不変（参照経路確認済み・Current Focus に記録）"
    falsification_test: "class_name_normalized 基準に変更後・unit test で syubetucd='12' + class_name_normalized='1勝クラス' が eligible にならない場合・または新馬以外が newcomer 不適格に残る場合・本 fix は不十分。"
    fix_rationale: "syubetucd は newcomer/maiden 判定の代理キーとして不適格（馬齢カテゴリとクラスが直交）。class_name_normalized が意味論的に正しい基準。label_version bump で新旧 universe を明示分離（§19.1）。feature snapshot 不変・Phase 11/12 凍結維持。"
    blind_spots: "（解消済み）class_name_normalized は _RACE_META_SELECT_COLUMNS に未 SELECT → fix で追加。feature snapshot は is_model_eligible で row filter しない → 再生成不要。Phase 11/12 参照経路 → label 再生成で上書きされない（確認完了）。"
    blind_spot_1_resolved: "compute_is_model_eligible の row に class_name_normalized は伝播していない。_RACE_META_SELECT_COLUMNS(L269-280) は class_code_normalized/class_level_numeric/class_normalization_status を SELECT するが class_name_normalized は未 SELECT。→ fix には _RACE_META_SELECT_COLUMNS へ class_name_normalized 追加 + race_merge 伝播が必要（compute_fukusho_labels L646-661 で race_extra_cols に class_name_normalized を含めれば伝播する・既存の race_date/syubetucd と同一経路）。"
    blind_spot_3_resolved: "feature snapshot は is_model_eligible で row filter しない（再生成不要・ユーザー案5通り）。src/model/data.py: (1) load_feature_matrix は Parquet のみ読込（SC#1 聖域・L249-276）(2) build_training_frame は feature_df と label_df を PK で left merge し filter_eligible 呼出（L393-428）(3) filter_eligible が label 側の is_model_eligible/label_validation_status で row filter（L431-449）。feature snapshot の row 構成は不変・label 側の is_model_eligible 値が変わるだけで build_training_frame の出力 row 数が変わる。"
    class_name_normalized_source: "src/config/class_normalization.yaml: jyokencd5='701' → class_name_normalized='新馬'。jyokencd5='703' → '未勝利'。jyokencd5='005' → '1勝クラス'。race 静的属性（PIT 安全）。normalize.py L83/L504 で normalized.n_race に text 列として格納済み。"
    existing_tests_to_update: "tests/test_fukusho_label.py: test_is_model_eligible_newcomer_syubetucd(L995・syubetucd='11' 前提) / test_is_model_eligible_maiden_syubetucd_included(L1006・syubetucd='13' 前提) / test_is_model_eligible_class_below_minimum(L1028・syubetucd='99' 異常) / _build_label_input_df(L100・race_df に class_name_normalized 未含む)。fix で class_name_normalized 基準に変更する場合・helper と上記3テストを更新必要。"
    label_regen_script: "scripts/run_label_etl.py が存在・run_label_etl(read_pool, write_pool) を2回連続実行し idempotent 検証（checksum 一致）+ raw 不変性検証（assert_raw_unchanged）。main が直接実行する場合は `uv run python scripts/run_label_etl.py`。"
- reasoning_checkpoint:
    hypothesis: "`compute_is_model_eligible` が newcomer 判定を `syubetucd in ['11','12']` で行い、`syubetucd='12'` を新馬と見做しているが、実データ（2023 n_race）では syubetucd='12' の 1039 レース中新馬は 45 のみ・994 は 1勝/未勝利。code_tables.yaml の '12'=3歳新馬 定義が不正確で、結果 JRA 最多の 1勝/未勝利層が newcomer 誤除外され universe が壊れる。"
    confirming_evidence:
      - "label_spec.yaml L85-87 で newcomer_syubetucd=['11','12']・code_tables.yaml L30 で '12'='3歳新馬（平地）'・fukusho_label.py L485-494 で syubetucd in ['11','12'] → newcomer 除外（3箇所連鎖）"
      - "ユーザー実データ検証（live-DB readonly・2023）: class_name_normalized='新馬' の syubetucd は '11'=257/'12'=45・syubetucd='12' の class_name_normalized サンプル=['1勝クラス','1勝クラス','1勝クラス','未勝利','未勝利']"
      - "label.fukusho_label 2023: eligible 22793 / ineligible 24879（うち newcomer 23383）= 1勝/未勝利層の大規模脱落と整合"
    falsification_test: "`class_name_normalized='新馬'` を newcomer 基準にしても eligible 数が 22793 付近から増加しない、または新馬以外のクラスが不適格に残るなら本仮説は不十分（別の誤除外経路が存在）。逆に syubetucd='12' の class_name_normalized が新馬のみなら本仮説は誤り（要全期間・全コード再確認）。"
    fix_rationale: "newcomer 判定を意味論的に正しい class_name_normalized='新馬' に変更。syubetucd はレース種別（クラス名と1:1でない混在コード）なので代理キーとして不適切。'12' の新馬 45 も class_name_normalized 基準なら正確に捕捉。code_tables.yaml の '12' 定義も実測（1勝/未勝利）に訂正。"
    blind_spots: "（1）解消済: class_name_normalized は compute_is_model_eligible row に未伝播・fix で _RACE_META_SELECT_COLUMNS と race_extra_cols へ追加必要。（2）解消済: 全期間で syubetucd='11'/'12' は新馬+未勝利+1勝+OP の混在・'13'/'14' は 1勝/2勝/3勝/OP の混在・'18'/'19' は未勝利+OP（障害）。（3）解消済: feature snapshot は is_model_eligible で row filter しない（src/model/data.py 確認）・再生成不要。（4）未解決（checkpoint 要件）: label_version bump 要否と Phase 11/12 凍結への影響・label 再生成実行権限。"
- tdd_checkpoint: (空)

## Evidence（live-DB readonly 検証・2026-06-28・statement_timeout 付与）

- timestamp: 2026-06-28
  checked: live-DB readonly で blind_spots (1)(3) の codebase 読込
  found:
    - "blind_spots(1)解消: compute_is_model_eligible の row に class_name_normalized は伝播していない。src/etl/fukusho_label.py の _RACE_META_SELECT_COLUMNS(L269-280) は class_code_normalized/class_level_numeric/class_normalization_status を SELECT するが class_name_normalized は未 SELECT。compute_fukusho_labels の race_extra_cols(L646-648) も class_name_normalized を含まない。fix では _RACE_META_SELECT_COLUMNS に class_name_normalized を追加 + race_extra_cols に 'class_name_normalized' を追加（race_date/syubetucd と同一経路で伝播）すれば compute_is_model_eligible row から参照可能になる。"
    - "blind_spots(3)解消: feature snapshot は is_model_eligible で row filter しない（ユーザー案5通り・再生成不要）。src/model/data.py: load_feature_matrix は Parquet のみ読込（SC#1 聖域・L249-276）・build_training_frame は feature_df と label_df を PK left merge し filter_eligible 呼出（L393-428）・filter_eligible が label 側の is_model_eligible で row filter（L431-449）。feature snapshot の row 構成は不変・label 側の is_model_eligible 値変更だけで build_training_frame の出力 row 数が変わる。"
    - "class_name_normalized の源: src/config/class_normalization.yaml jyokencd5_map（jyokencd5='701'→'新馬'/'703'→'未勝利'/'005'→'1勝クラス'...）。jyokencd5 は race 静的属性（出馬表確定時に既知・PIT 安全）。src/etl/normalize.py L83/L504 で normalized.n_race.class_name_normalized (text) として格納済み・39478/39593 が non-NULL。"
    - "label 再生成スクリプト: scripts/run_label_etl.py が存在・run_label_etl を2回連続実行し idempotent 検証（checksum 一致）+ assert_raw_unchanged で raw 不変性証明。"
    - "既存テスト更新要: tests/test_fukusho_label.py の _build_label_input_df(L100・race_df に class_name_normalized 未含む) と test_is_model_eligible_newcomer_syubetucd(L995・syubetucd='11' 前提)/test_is_model_eligible_maiden_syubetucd_included(L1006・syubetucd='13' 前提)/test_is_model_eligible_class_below_minimum(L1028・syubetucd='99' 異常)。fix で class_name_normalized 基準に変更する場合 helper と上記3テスト更新必要。"
  implication: "blind_spots (1)(3) 解消。fix の技術的実現性確認（class_name_normalized 伝播は race_extra_cols 追加で対応可能・feature snapshot 再生成不要）。残るは label_version/snapshot/Phase11-12 の判断（main の聖域）。"

- timestamp: 2026-06-28
  checked: live-DB readonly で全期間（2015以降）の syubetucd × class_name_normalized 分布（blind_spots (2)）
  found:
    - "class_name_normalized='新馬'（全期間・3309 races）: syubetucd='11'=2710 races / syubetucd='12'=599 races。→ 新馬は '11'/'12' 両方に散在・'11' が多数。2023 単独（302 races）でも '11'=257/'12'=45 とユーザー報告と整合。"
    - "syubetucd='11'（code_tables は '2歳新馬'）の実態: 未勝利=3623 / 新馬=2710 / 1勝クラス=363 / OP・重賞=328 races。→ 新馬は多数派ですらない。code_tables.yaml の '11'='2歳新馬（平地）' は不正確。"
    - "syubetucd='12'（code_tables は '3歳新馬'）の実態: 未勝利=9611 / 1勝クラス=1559 / OP・重賞=629 / 新馬=599 races。→ 新馬は最少。code_tables.yaml の '12'='3歳新馬（平地）' は全面矛盾（9611+1559+629=11799 races が新馬以外）。"
    - "syubetucd='13'（code_tables は '2歳未勝利'）の実態: 1勝クラス=5657 / 2勝クラス=2819 / 3勝クラス=1198 / OP・重賞=1069 races。→ 未勝利・新馬は0件。code_tables.yaml の '13'='2歳未勝利（平地）' は全面矛盾。"
    - "syubetucd='14'（code_tables は '3歳未勝利'）の実態: 1勝クラス=3630 / 2勝クラス=2372 / 3勝クラス=1076 / OP・重賞=906 races。→ 未勝利・新馬は0件。code_tables.yaml の '14'='3歳未勝利（平地）' は全面矛盾。"
    - "syubetucd='18'/'19'（障害・code_tables は正）: 未勝利 + OP・重賞 + (NULL) の混在。障害コードとしては正しいが・class_name_normalized も未勝利/OP に分かれる。"
    - "syubetucd は馬齢カテゴリ（2歳/3歳/古馬）を表すコードであって・クラス（新馬/未勝利/1勝...）とは直交する軸。class_name_normalized がクラスの唯一の正しい指標。memory jra-van-babacd-trackcd-code-system（TrackCD/BabaCD の CODE.md 不完全）と同系列の 'syubetucd 定義不正確' 問題。"
  implication: "blind_spots (2) 解消。仮説強く確認: syubetucd は newcomer 判定の代理キーとして不適格。class_name_normalized='新馬' 基準への変更が意味論的に正しい。code_tables.yaml の '11'/'12'/'13'/'14' 定義は全面訂正必要（'18'/'19' は正）。"

- timestamp: 2026-06-28
  checked: live-DB readonly で修正前後の eligible 数予測（2023・47672 馬行）
  found:
    - "label.fukusho_label 現状（2023）: eligible=22793 / ineligible(newcomer)=23383 / ineligible(obstacle)=1460 / ineligible(race_or_horse_cancelled)=36。TOTAL=47672。ユーザー報告と完全一致。"
    - "修正後予測（2023・class_name_normalized='新馬' 基準）: other_eligible_or_nonewcomer=22829 / eligible_recovery_was_newcomer=19452 / newcomer_proposed=3931 / obstacle=1460。TOTAL=47672。"
    - "修正後 eligible 予測 = 22829 + 19452 = 42281 horses（現在 22793 から +19452 の大幅増・falsification_test 'eligible 数が増加しない' を明確に反証）。"
    - "newcomer_proposed=3931 は class_name_normalized='新馬' のみに正確に縮小（現在の newcomer 23383 から 3931 へ・誤除外 19452 が解消）。"
    - "修正後 eligible 候補 42281 の内訳（新馬以外・障害以外）: 未勝利(syubetucd='11'/'12')=16584 / 1勝クラス=12450 / 2勝クラス=6323 / 3勝クラス=3084 / OP・重賞=3840 馬。JRA の現実的な出走馬層と整合。"
    - "特筆: 未勝利 syubetucd='11'=4184/'12'=12400 計16584馬が現在新comer誤除外。JRA で最多の未勝利層が脱落していた。"
  implication: "仮説確認完了。修正後は JRA の現実的な出走馬層（1勝/未勝利/2勝/3勝/OP の全て）を覆盖する universe になる。falsification_test 反証済み。"

- timestamp: 2026-06-28
  checked: live-DB readonly で class_eligibility.maiden_syubetucd=['13','14','15'] の実効性検証（全期間）
  found:
    - "class_level_numeric=0（未勝利・新馬相当）の syubetucd 分布（全期間）: syubetucd='12'/未勝利=9611 / '11'/未勝利=3623 / '11'/新馬=2710 / '12'/新馬=599 / '18'/未勝利=515 / '19'/未勝利=442 races。"
    - "現在の maiden_syubetucd=['13','14','15'] には '11'/'12' が含まれない。未勝利の大部分（syubetucd='11'/'12' の 13234 races）は step(b) newcomer で先に除外され step(f) の maiden 救済ロジックに到達しない。→ maiden_syubetucd 救済は実質到達不能（不具合）。"
    - "fix で newcomer 基準を class_name_normalized='新馬' に変更する場合・maiden 救済も class_name_normalized='未勝利' 基準に直す必要がある。現在の maiden_syubetucd=['13','14','15'] は syubetucd='13'/'14' が 1勝/2勝/3勝/OP の混在（未勝利0件）のため・これも実態と矛盾。"
  implication: "fix の範囲拡大: label_spec.yaml の newcomer_syubetucd だけでなく class_eligibility.maiden_syubetucd も class_name_normalized 基準に変更する必要がある。現在の maiden_syubetucd は構造的に到達不能だが・新馬を class_name_normalized 基準で除外するようにすると未勝利（class_level_numeric=0）が step(f) に到達するようになり・そこで maiden_syubetucd=['13','14','15'] では未勝利(syubetucd='11'/'12')を救済できない。class_name_normalized='未勝利' を救済基準に直す。"

- timestamp: 2026-06-28
  checked: Phase 11/12 参照経路の確認（fix 適用前・凍結維持の前提）
  found:
    - "label.fukusho_label テーブルは独立（label スキーマ）。label 再生成（run_label_etl）は同テーブルのみ更新。"
    - "prediction.fukusho_prediction テーブルは model_type+model_version+feature_snapshot_id+as_of_datetime スコープで独立（src/db/prediction_load.py:313 model_version スコープ DELETE→INSERT）。is_model_eligible 列を持たない（src/db/schema.py:61-98 に is_model_eligible 無し・provenance + 予測値のみ）。label 再生成の影響を受けない。"
    - "reports/11-evaluation/, reports/12-evaluation/ の JSON/MD は Phase 11/12 評価スクリプト（run_phase11_evaluation.py / run_phase12_evaluation.py）が atomic write で生成した凍結ファイル。label 再生成（run_label_etl.py）だけではこれらのファイルは上書きされない。"
    - "run_phase11_evaluation.py:326,384,413 は label_version='v1.0' をハードコード（Phase 11 評価時の universe は v1.0 universe）。label 再生成で label.fukusho_label.is_model_eligible が変わっても・Phase 11/12 スクリプトを再実行しない限り reports/*.json は不変。"
    - "feature snapshot（snapshots/*.parquet）は is_model_eligible で row filter しない（src/model/data.py: load_feature_matrix は Parquet のみ・filter_eligible は label 側 row filter）。label 再生成で feature snapshot は不変。"
  implication: "Phase 11/12 凍結維持の前提確認完了。label 再生成（main 実行）は label.fukusho_label テーブルのみ更新。prediction テーブル・reports/*.json・feature snapshot は全て不変。"

- timestamp: 2026-06-28
  checked: fix 適用（4ファイル）と unit test / ruff 検証
  found:
    - "fix 適用完了: (1) src/config/label_spec.yaml: label_generation_version v1.0.0→v1.1.0・newcomer_syubetucd 廃止→newcomer_class_name=['新馬']・class_eligibility.maiden_syubetucd 廃止→maiden_class_name=['未勝利']・_REQUIRED_SPEC_KEYS 更新 (2) src/etl/fukusho_label.py: _RACE_META_SELECT_COLUMNS に class_name_normalized 追加・compute_is_model_eligible で class_name_normalized 判定・race_extra_cols 伝播・docstring 更新 (3) src/config/code_tables.yaml: syubetucd 定義を実測に訂正（'11'/'12'/'13'/'14' は混在コード） (4) tests/test_fukusho_label.py: _build_label_input_df に class_name_normalized 追加・既存3テスト更新・新規回帰テスト2件追加（newcomer_misclassification_regression / syubetucd11_non_newcomer_eligible）"
    - "unit test 結果: KEIBA_SKIP_DB_TESTS=1 で tests/test_fukusho_label.py 全48テスト GREEN（1.05s）。新規回帰テスト含む。"
    - "ruff 結果: 変更前19エラー・変更後18エラー（エラー減少・既存パターン踏襲）。E712 は既存51箇所の # noqa: E712 パターンに整合。私の変更で新規エラーなし。"
    - "リーク安全性確認: class_name_normalized は jyokencd5（最若年条件コード・race 静的属性・出馬表確定時に既知）から機械導出（src/config/class_normalization.yaml: jyokencd5='701'→新馬/'703'→未勝利/'005'→1勝クラス）。PIT 安全（feature_cutoff_datetime 以前に確定）・リークを導入しない。"
  implication: "fix 適用完了・unit test GREEN・ruff 整合・リーク安全性確認完了。main へ引き渡し可能（label 再生成は main が実行）。"

- timestamp: 2026-06-28
  checked: label 再生成（live-DB 書込・main 直接実行 `uv run python scripts/run_label_etl.py`）と新 universe 検証
  found:
    - "label ETL run #1/#2: rows_inserted=554267・raw_touched=False・checksum=43a5e07b99d4107692938da900468602（両回同一）・idempotent 検証 PASS（HIGH #3）"
    - "raw 不変性: PASS（row-hash + row-count + pg_stat 全て不変・D-06 聖域クリア）"
    - "label_generation_version: v1.1.0（554267 行全て・SELECT 確認）"
    - "2023 eligible split: eligible=42214 / ineligible=5458（newcomer=3931・obstacle=1460・race_or_horse_cancelled=67）・total=47672"
    - "修正前後比較: eligible 22793→42214（+19421・JRA 最多の 1勝/未勝利層復帰）・newcomer 23383→3931（誤除外 19452 解消・class_name_normalized='新馬' のみに縮小）・obstacle 1460→1460（不変・syubetucd 基準は正）"
    - "予測値（eligible 42281）との差 67 = race_or_horse_cancelled 増分（36→67・label 再生成タイミングのデータ経時変化・fix 影響なし）"
  implication: "label 再生成成功・新 universe は JRA の現実的な出走馬層（1勝/未勝利/2勝/3勝/OP）を覆盖・聖域全クリア（idempotent・raw 不変・Phase 11/12 凍結維持・§19.1 label_version v1.1.0 分離）"

## Resolution

root_cause: |
  newcomer/maiden 判定基準が syubetucd（馬齢カテゴリ混在コード）だったため・JRA 最多の
  1勝/未勝利層が newcomer として誤除外され universe が壊れていた。syubetucd は馬齢カテゴリ
  （2歳/3歳/古馬）とクラス（新馬/未勝利/1勝...）が直交する混在コードで・newcomer/maiden
  判定の代理キーとして不適格。実測: syubetucd='12' は未勝利9611/1勝1559/OP629/新馬599 races
  （新馬は最少）。正しい基準は class_name_normalized（jyokencd5 由来・'新馬'/'未勝利'/'1勝クラス'）。
  併せて maiden_syubetucd=['13','14','15'] も syubetucd='13'/'14' が未勝利0件のため構造的到達不能だった。
fix: |
  newcomer/maiden 判定基準を syubetucd から class_name_normalized に変更（v1.1.0 bump）。
  (1) label_spec.yaml: newcomer_class_name=['新馬'] / maiden_class_name=['未勝利'] / label_generation_version v1.1.0
  (2) fukusho_label.py: _RACE_META_SELECT_COLUMNS に class_name_normalized 追加・compute_is_model_eligible で class_name_normalized 判定・race_extra_cols 伝播
  (3) code_tables.yaml: syubetucd 定義を実測に訂正（馬齢カテゴリ混在コード明記）
  (4) test_fukusho_label.py: 既存3テスト更新 + 新規回帰テスト2件追加
verification: |
  unit test GREEN（KEIBA_SKIP_DB_TESTS=1・tests/test_fukusho_label.py 全48テスト）。
  ruff 整合（変更前19エラー・変更後18エラー・新規エラーなし）。
  Phase 11/12 参照経路確認（label 再生成で prediction/reports/feature snapshot 不変）。
  リーク安全性確認（class_name_normalized は PIT 安全）。
  label 再生成（live-DB・main 直接実行 `uv run python scripts/run_label_etl.py`）:
  idempotent PASS（run #1/#2 同一 checksum 43a5e07b99d4107692938da900468602・HIGH #3）・
  raw 不変 PASS（D-06）・label_generation_version=v1.1.0（554267 行全て）・
  2023 eligible 22793→42214（+19421・JRA 最多の 1勝/未勝利層復帰）・
  newcomer 23383→3931（class_name_normalized='新馬' のみに縮小・誤除外 19452 解消）・
  obstacle 1460→1460（不変・syubetucd 基準は正）。
files_changed:
  - src/config/label_spec.yaml
  - src/etl/fukusho_label.py
  - src/config/code_tables.yaml
  - tests/test_fukusho_label.py
