# Phase 8: Adversarial Audit Suite - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Build-Order DAG の最終段（cross-cutting）—— **Phase 1-7 をまたぐリーク防止テストスイート（TEST-01）を統合・GREEN化** し、"Looks Done But Isn't" を検出する**対抗的監査（adversarial audit）テスト**を補完して、v1 マイルストーン出荷前の受け入れゲートとする。

具体的には:

1. **既存テストの集約・可視化** — Phase 1-7 で蓄積した `tests/` 配下 49ファイル・476テスト関数（SC#1/#2 のほぼ全リークサーフェスを個別に既カバー）を、サーフェス別カバレッジマップ／SC#1-#3 対応表として集約し「どこが検証済みか」を一枚の監査レポートに見える化する
2. **対抗的監査テストの補完** — 機能テストでは拾えない静かな故障モード（SC#2 が明示する3ケース: lookahead 注入検出 / payout 正欠損検出 / fold の train/test `race_id` 共有検出）を、**リークを注入すると fail する独立 adversarial テスト**として `tests/audit/` に新設する
3. **フルスイート GREEN 証明** — `KEIBA_SKIP_DB_TESTS` unset で全 `requires_db`（live PostgreSQL）を含むフルテストスイートを実行し GREEN を証明する（Phase 4「unset 最終ゲート」の先例踏襲）
4. **再現性スモークの統合（SC#3）** — フルパイプライン（snapshot→train→predict→backtest→eval）が固定 seed で同一結果を再現することを、既存 CLI（`run_train_predict --check-reproduce` 等）＋ pytest を束ねる単一 smoke スクリプトで確認する
5. **出荷ゲート証憑の生成** — 上記を `reports/08-audit.{md,json}` にまとめ、**既知の限界（回収率~0.65天井・odds JODDS再検証subject・Calibration で BL 劣位）を隠さず "Known Limitations" として明示**し、honest な出荷判定資料とする

**境界＝検証ゲート。** Phase 8 は**監査・統合・再現性証明のみ**。新規の予測ロジック・モデル・backtest 戦略・UI 機能は作らない（Phase 1-7 の stamped 実装を監査対象とする）。07-CONTEXT が Deferred した「UI/CSV の read-only 保証・再現性スタンプ inline 検出」の対抗的監査も本フェーズに含む（TEST-01「対抗的監査テストを含む」に合致・Phase 7 スコープ外明示の継承）。

</domain>

<decisions>
## Implementation Decisions

### 統合成果物の形（TEST-01 / SC#1・SC#2）
- **D-01: 両方（監査レポート集約可視化 ＋ 新規 adversarial テスト新設）** — `reports/08-audit.{md,json}`（サーフェス別カバレッジマップ・SC#1/#2/#3 対応表）で既存476テストを集約・可視化し、真のギャップ（SC#2 注入ケース等・UI/CSV 監査）は `tests/audit/` に新設して補完する。「どこカバー済み／どこに注入テストを足すか」を明示でき、TEST-01「リーク防止の対抗的監査テストを含む」に最適合。ユーザー選択: 両方。（監査レポート集約のみ / 新規テスト新設のみ は却下）

### 対抗的（注入型）テストの深度（SC#2）
- **D-02: SC#2 必須3ケース中心** — SC#2 が明示する3ケース（**lookahead 注入検出** / **payout 払戻対象正の馬のラベル欠損検出** / **fold の train/test が `race_id` を共有する検出**）を、それぞれ**リークを注入すると fail する独立 adversarial テスト**として確保する。既存476テストが各サーフェスの functional 検証を担い、注入型（mutation/injection style）はこの3つを代表とする。`test_no_target_encoding_leak`（Phase 4・意図的リーク注入で DEMONSTRABLY fail を実証済み）が再利用すべきパターン。ユーザー選択: SC#2必須3ケース中心。（全8サーフェス展開 / Claude判断 は却下）

### 再現性スモーク（SC#3）
- **D-03: 既存 CLI＋pytest を束ねる統合スクリプト** — `run_train_predict --check-reproduce`（Phase 4 SC#4 bit-identical）＋ 既存 bit-identical pytest 群 ＋ backtest/eval 再現確認を、`scripts/run_reproducibility_smoke.py`（or Make ターゲット）で orchestrate し、SC#3「snapshot→train→predict→backtest→eval の固定 seed 再現」を単一エントリポイントで確認する。新規のフルパイプライン runner は作らず既存資産を活用（重複回避・keep it simple）。ユーザー選択: 既存CLI+pytestを束ねる。（新規統合smoke runner / Claude判断 は却下）

### DB 必須テストと出荷ゲート証憑（SC#1 GREEN 証明）
- **D-04: KEIBA_SKIP_DB_TESTS unset 全実行 ＋ reports/08-audit 生成** — Phase 4 踏襲。`KEIBA_SKIP_DB_TESTS` を unset し、live PostgreSQL（everydb2）の全 `requires_db` テストを含むフルスイートを実行して GREEN を証明する。`reports/08-audit.{md,json}`（サーフェス別 GREEN/カバレッジ・SC#1/#2/#3 対応表・Known Limitations）を v1 出荷ゲートの証憑として生成する。memory `phase7-ui-live-db-bugs`（live-DB でしか発覚しない bug あり・unit test の SKIP では検出不可）に整合。ユーザー選択: unset全実行+監査レポート。（CI(DB不要)+手動live-DB分離 / Claude判断 は却下）

### honest 既知限界の可視化（"Looks Done But Isn't" ゲートの核心）
- **D-05: Known Limitations セクションで既知限界を明示** — `reports/08-audit` に "Known Limitations" セクションを設け、**回収率~0.65 天井（odds-free 1-A の構造的限界・閾値では改善しない）**・**Phase 5 odds の JODDS取得完了後の再検証 subject**・**Phase 4 SC#2 で主モデルが Calibration において BL-1/BL-4 に劣位** を隠さず明示する。本プロジェクトの Core Value（過大表示回避・honest 評価・実馬券購入しない個人分析）に整合。memory `fukusho-recovery-070-structural-ceiling` に整合。ユーザー選択: 含める。（含めない / Claude判断 は却下）

### Phase 7 継承の UI/CSV 対抗的監査（TEST-01）
- **D-06: Phase 8 スコープに含める** — 07-CONTEXT が Deferred した「UI/CSV の read-only 保証（書き込み経路不存在）・再現性スタンプ inline 検出（スタンプ欠落検出）」の対抗的監査テストを `tests/audit/` に追加する。TEST-01「対抗的監査テストを含む」に合致・Phase 7 が明示的に本フェーズに委ねた項目。SC#1 の明示サーフェスリストには現れないが、07-CONTEXT Deferred と TEST-01 の包括表現でスコープ内。memory `phase7-ui-live-db-bugs`（live-DB 必須 bug）への対処も兼ねる。ユーザー選択: 含める。（含めない / Claude判断 は却下）

### Claude's Discretion（研究者/計画者に委ねる）
- **`tests/audit/` の内部構成** — ファイル分割単位（サーフェス別 `test_audit_label.py` / `test_audit_features.py` / `test_audit_split.py` / `test_audit_odds.py` / `test_audit_ui_csv.py` 等 vs 単一ファイル）・各 adversarial テストの注入手法（合成 DataFrame で T+1 データを混入等）は planner/researcher が決定。`test_no_target_encoding_leak` の既存パターンを踏襲。
- **サーフェス別カバレッジマップの機械化** — `reports/08-audit.json` を pytest 収集から自動生成するか（`--collect-only` + marker 設備）、手動で SC↔テスト対応表を保守するか。既存の md+json 分離 reports 慣例に従う。
- **adversarial 3ケースの「既存テストとの棲み分け」** — `test_pit_cutoff` / `test_label_reconcile` / `test_group_split` に既に同等の注入ケースが存在する場合は重複を避け、真のギャップだけ新設するか否か（researcher の棚卸し結果次第）。
- **再現性スモークの対象データ規模** — `run_reproducibility_smoke.py` を合成データで回すか、stamped snapshot の縮小サンプルで回すか（live-DB 全量は重い）。Phase 4 SC#4 の合成データ bit-identical 手法を参考。
- **CI 統合の要否** — config.json に CI 設定なし。個人開発ローカル（PostgreSQL 15.18 Homebrew）。pre-commit / push hook で DB 不要層だけ回す等は Phase 8 では最小限（D-04 の unset 全実行が主）。将来の PHASE2/OPS で拡張。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §17.3 — テスト必須領域（ラベル/PIT/split ロジックの unit test 義務・高リーク面のテスト）。TEST-01/本フェーズの直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §19.1 — 再現性（モデル版・特徴量 snapshot・ラベル版・`odds_snapshot_policy`・`backtest_strategy_version` の保存・同条件で再学習・再現）。D-03/D-04/SC#3 の根拠
- `docs/keiba_ai_requirements_v1.3.md` §15.2 / §15.3 — キャリブレーション受け入れゲート（`sum(p)` 分布・monotone bin・yearly inversion 禁止）。Known Limitations（D-05）の Calibration 劣位記載の文脈
- `docs/keiba_ai_requirements_v1.3.md` §11.6 — 回収率計算（Known Limitations の回収率天井記載の意味）
- `docs/keiba_ai_requirements_v1.3.md` §13.2 / §13.4 — feature_cutoff_datetime 規律・禁止列（SC#1 サーフェス「feature_cutoff_datetime enforcement」/SC#2「lookahead 注入検出」の根拠）
- `docs/keiba_ai_requirements_v1.3.md` §10.5 — 払戻テーブル突合 6検査（SC#1「payout-table reconciliation」/SC#2「payout 正欠損検出」の根拠）

### プロジェクト計画・状態（正）
- `.planning/ROADMAP.md` — **Phase 8 成功基準 #1-#3**（#1 フルスイート GREEN・8サーフェス列挙 / #2 adversarial 3ケース明示 / #3 reproducibility smoke-test path 統合）・8フェーズ strict DAG の最終フェーズ・TEST-01 割当
- `.planning/REQUIREMENTS.md` — **TEST-01**（複勝ラベル・払戻突合・取消/除外/中止・オッズ時点固定・仮想購入・`feature_cutoff_datetime`・評価指標・`race_id`単位分割・クラス正規化・カテゴリ/欠損処理 の各サーフェステスト＋リーク防止の対抗的監査テストを含む）・全25要件トレーサビリティ（TEST-01 のみ Phase 8 割当・Pending）
- `.planning/STATE.md` — Phase 8 移行状態（status: verifying・37/37 plans complete・Phase 07 complete）
- `CLAUDE.md` — §17.3 テスト必須・§19.1 再現性・リーク防止聖域・KEIBA_SKIP_DB_TESTS 運用・「許可済み操作は自分で実行」

### 前フェーズ成果（引き継ぎ決定の正・監査対象）
- `.planning/phases/07-presentation/07-CONTEXT.md` — **Deferred: UI/CSV の read-only 保証・再現性スタンプ inline 検出の対抗的監査（Phase 8 委譲）**。D-06 の直接の前提
- `.planning/phases/04-model-prediction/04-CONTEXT.md` — **SC#3 対抗的構造診断（`test_no_target_encoding_leak`・注入で DEMONSTRABLY fail）/ SC#4 bit-identical（`run_train_predict --check-reproduce`・num_threads=1/seed=42/FIXED_REPRODUCE_TS）/ KEIBA_SKIP_DB_TESTS unset 最終ゲート（38 requires_db 全実行・262 passed）**。D-02/D-03/D-04 の先例
- `.planning/phases/06-evaluation-calibration-gates/06-CONTEXT.md` — **キャリブ指標再設計（quantile/ECE/MCE 併記・uniform max_dev は低分散 BL を不当有利化）**。D-05 Known Limitations の Calibration 記載の文脈
- `.planning/phases/05-ev-backtest/05-CONTEXT.md` — **実データ backtest 25件完走（odds 正確性は JODDS取得後再検証 subject・manual-only 分離）**。D-05 Known Limitabilities の odds 記載の文脈
- `.planning/phases/03-as-of-features-snapshots/03-CONTEXT.md` — **feature_availability registry・fail-loud allowlist・merge_asof PIT**。SC#1「feature_cutoff_datetime enforcement」/SC#2「lookahead 注入検出」の監査対象

### コード契約（監査対象・scout 確認済み）
- `tests/conftest.py` / `tests/{ev,features}/conftest.py` — **`KEIBA_SKIP_DB_TESTS` skipif 機構・`requires_db` marker**。D-04 の実行基盤
- `pyproject.toml` `[tool.pytest.ini_options]` — **`requires_db` marker 登録済み・`testpaths=["tests"]`・`addopts="-ra"`**。テスト実行設定の正
- `tests/features/test_pit_cutoff.py` / `tests/test_label_reconcile.py` / `tests/utils/test_group_split.py` — SC#2 の3ケース（lookahead/payout正欠損/fold共有）に近接する既存テスト。D-02 の棚卸し対象（重複回避）
- `tests/model/test_trainer.py`（`test_no_target_encoding_leak`）— **注入型 adversarial テストの再利用パターン**。D-02 の鋳型
- `tests/model/test_calibrator.py`（`test_reproduce_bit_identical`）/ `scripts/run_train_predict.py`（`--check-reproduce`）— SC#3 再現性スモークの既存資産
- `tests/ev/test_run_backtest_e2e.py` / `scripts/run_backtest.py` / `scripts/run_evaluation.py` — backtest/eval 再現性の既存資産・`scripts/run_*.py` CLI 慣例
- `src/ev/report.py`（md+json 分離・presence assert）— `reports/08-audit.{md,json}` 生成の DRY パターン（reports/ 慣例）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **既存476テスト資産（49ファイル）** — `tests/{db,ev,features,model,ui,utils}` ＋ ルート8ファイル。SC#1/#2 のほぼ全サーフェス（ラベル/払戻/取消除外中止/オッズ時点/仮想購入/cutoff/分割/クラス正規化/カテゴリ欠損）を個別テストで既カバー。Phase 8 はこれを「集約可視化」し「真のギャップ」だけ補完する
- **`test_no_target_encoding_leak`（Phase 4）** — 意図的リーク注入で DEMONSTRABLY fail する adversarial テストの鋳型。SC#2 の3ケース（lookahead/payout正欠損/fold共有）の注入手法の直接の再利用元
- **`run_train_predict.py --check-reproduce`（Phase 4 SC#4）** — 固定 seed bit-identical 再現性インフラ。SC#3 smoke の中核資産
- **`KEIBA_SKIP_DB_TESTS` + `requires_db` marker（conftest.py / pyproject.toml）** — DB 必須テストの skip/実行制御。D-04 unset 全実行ゲートの土俵（Phase 4 で 38 requires_db 全実行・262 passed の実績）
- **`src/ev/report.py`（md+json 分離・presence assert[LOW-05]）** — `reports/08-audit.{md,json}` 生成の DRY 列定数＋検証パターンの再利用元

### Established Patterns
- **reports/ の md + json 分離出力** — Markdown（人間確認）と JSON（byte-reproducible・機械消費）の分離。`reports/04-eval` / `05-backtest` / `06-evaluation` / `06-segments` 慣例。`reports/08-audit` も踏襲
- **pytest marker 設備** — `requires_db` marker 登録済み。`tests/audit/` の新規 adversarial テストも合成データ中心（DB 不要）で設計可能
- **`scripts/run_*.py` CLI 慣例** — argparse・reports/ 出力・`KEIBA_SKIP_DB_TESTS` ゲート。`scripts/run_reproducibility_smoke.py`（D-03）が踏襲
- **対抗的構造診断の正直な命名** — Phase 4 SC#3 が「live-data 証明と称さず対抗的構造診断と正確に呼ぶ」を実践。SC#2 注入テストも合成データによる構造実証として正直に記述

### Integration Points
- **新規（監査・統合層・書き込み DB なし）:**
  - `tests/audit/`（新規・SC#2 の3ケース注入テスト ＋ D-06 UI/CSV 監査）
  - `scripts/run_reproducibility_smoke.py`（新規・SC#3・既存 CLI/pytest を orchestrate）
  - `reports/08-audit.{md,json}`（新規・サーフェス別カバレッジマップ・SC対応表・Known Limitations・出荷ゲート証憑）
- **READ（監査対象・既存）:**
  - `tests/` 配下全476テスト（カバレッジマップ集約元）
  - `pyproject.toml` `[tool.pytest.ini_options]`（marker/testpaths）
  - `conftest.py` 群（skip 機構・fixture）
- **CONSUMED BY（下流）:**
  - v1 マイルストーン出荷判定（`/gsd-complete-milestone` / `/gsd-audit-milestone`）— `reports/08-audit` が出荷ゲート証憠
  - 将来 PHASE2/PHASE3（モデル拡張時の回帰テスト基盤として `tests/audit/` が再利用）

</code_context>

<specifics>
## Specific Ideas

- **SC#1/#2 のサーフェスは既に個別テストでカバー済み** — scout 結果: `test_fukusho_label`(ラベル) / `test_label_reconcile`(払戻突合) / `test_refund_accounting`(取消除外中止) / `test_odds_snapshot`(オッズ時点) / `test_pit_cutoff`(cutoff) / `test_group_split`(race_id分割) / `test_class_normalization`(クラス正規化) / `test_trainer`(カテゴリ欠損)。Phase 8 の付加価値は「これらを一枚の監査レポートに集約可視化し、注入型 adversarial で静かな故障を補完すること」——新規に functional テストを大量に書き直すわけではない
- **SC#2 の3ケースと既存テストの対応** — lookahead 注入→`test_pit_cutoff`、payout 正欠損→`test_label_reconcile`、fold 共有→`test_group_split` に近接。researcher が「独立した注入→fail ケースとして存在するか」を棚卸し、真のギャップだけ `tests/audit/` に新設（重複回避）
- **"Looks Done But Isn't" の核心は honest な限界の可視化** — テストが全 GREEN でも、回収率天井・odds 再検証未完・Calibration BL 劣位は「出来ているように見えて本質的に限界がある」事象。D-05 Known Limitations は機能テストでは表現できない「概念的正直さ」を監査レポートで担保する。本プロジェクトが実馬券購入しない個人分析ツールである前提と整合
- **Phase 4 の「KEIBA_SKIP_DB_TESTS unset 最終ゲート」は Phase 8 の直接の先例** — 38 requires_db 全実行・262 passed・0 skipped を実証済み。D-04 はこれを Phase 8 全体に拡張適用する
- **live-DB でしか発覚しない bug ずれの防止** — memory `phase7-ui-live-db-bugs`（sys.path ガード・SQL 引用符・Streamlit deprecation が unit test の SKIP では検出不可だった実績）。D-04 unset 全実行 ＋ D-06 UI/CSV 監査は、この「unit test では見えない live-DB bug」を Phase 8 で確実に検出する設計
- **再現性スモークは「束ねる」で十分** — Phase 4 SC#4 が既に bit-identical を確立済み。新規フルパイプライン runner は Phase 4 と重複し keep it simple に反する。D-03 は既存 `--check-reproduce` + pytest + backtest/eval を orchestrate する薄いスクリプトで SC#3 を満たす

</specifics>

<deferred>
## Deferred Ideas

- **CI 環境での自動テスト実行（PHASE2 / OPS-01・02）** — GitHub Actions 等 CI での DB 不要層自動実行・push hook・pre-commit 連携。Phase 8 は個人開発ローカル（PostgreSQL 15.18 Homebrew）の unset 全実行（D-04）が主。CI 統合は将来フェーズ
- **MLflow/Optuna 連携のテスト基盤（OPS-01/02・§21 defer）** — モデル管理・ハイパラ最適化の回帰テスト。Phase 1 安定後・将来 PHASE2+
- **より広範な mutation testing / property-based testing 導入** — D-02 の注入型 adversarial を全サーフェスに一般化・`hypothesis` 等の property-based testing。現状は SC#2 の3ケース中心（D-02）。徹底度を上げる場合は将来フェーズで評価
- **フルパイプライン end-to-end runner の一本化** — D-03 は既存資産を束ねる薄いスクリプト。snapshot→...→eval を完全一本化した重厚 runner は、Phase 4 SC#4 と重複するため見送り。需要が出れば将来

### Reviewed Todos (not folded)
- **`.planning/todos/phase3-advisory-hardening.md`** — 「Phase 03 advisory 4件 hardening — Phase 3.1 に統合」。Phase 3.1 で既に解決済み・Phase 8（Adversarial Audit Suite）とは無関係（match score 0.6 は keyword "phase" のみの偶発一致）。Phase 8 スコープには畳み込まず。

</deferred>

---

*Phase: 8-Adversarial Audit Suite*
*Context gathered: 2026-06-24*
