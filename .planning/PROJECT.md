# Keiba AI v3（競馬予測AI）

## What This Is

JRA競馬データを用いて、各出走馬の**複勝払戻対象確率 `p_fukusho_hit`** を推定し、取得時点の複勝オッズと比較することで、複勝期待値（EV）が高い馬を抽出する予測AI。能力予測とEV計算を分離し、オッズはEV判定にのみ使用する（モデル特徴量には入れない）。穴馬の1着予測ではなく、過小評価されている馬の複勝払戻対象入り可能性を検出することを主目的とする。個人開発者自身による競馬分析・検証ツールであり、実馬券購入は行わない。

要件の正は `docs/keiba_ai_requirements_v1.3.md`（v1.3、改訂4版、Phase 1実装着手可のレビュー版）。本ファイルと要件に乖離がある場合は要件定義書を優先する。

## Core Value

オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性を**リークなく**検出し、race_id単位・時系列順の再現可能なバックテストでその有効性を定量評価できること。それ以外がすべて失敗しても、この再現性とリーク防止だけは守らなければならない。

## Requirements

### Validated

- [x] EveryDB2由来PostgreSQLデータの品質確認（主要テーブル・件数・日付範囲・NULL・重複・文字化け・コード異常）— Validated in Phase 1: Trust & Foundation（hybrid quality gate D-01、verdict=pass・BLOCK/INFO 分離）
- [x] normalized層の初期ETL（型変換・コード変換・クラス正規化）— Validated in Phase 1: Trust & Foundation（全 varchar 明示キャスト + class_normalization.yaml 機械導出・raw 不変性 D-06 を REVOKE + fingerprint で実証）
- [x] 複勝ラベル `fukusho_hit` の生成と払戻テーブル突合（発売開始時点ベース、`sales_start_entry_count` 取得・復元含む）— Validated in Phase 2: Fukusho Labels（2層 raw/validated label + D-04 4値 status・§10.5 6検査 BLOCK/INFO ゲート・>99.9% agreement 実測 100.0%・idempotent staging-swap・raw 不変・label.fukusho_label 554,267行）
- [x] as-of特徴量管理（`as_of_datetime` / `feature_cutoff_datetime` / `feature_availability` によるリーク防止）— Validated in Phase 3: As-of Features & Snapshots（PIT-correct feature builder + 不変 versioned Parquet・3者 registry parity・WR-01 PIT pre-filter on estimated_running_style・CR-02 JOIN 両側 filter・CR-03 race_date fail-loud・CR-04 joblib→JSON・live snapshot 554,267行 byte-reproducible・verification passed 4/4）
- [x] 複勝EV計算（`EV_lower` / `EV_upper`）と推奨ランク算出 — Validated in Phase 5: EV & Backtest（EV-01/EV-02・純粋関数 ev_rank/purchase_simulator/metrics/bl3_betting・§11.1/11.4/11.5/11.6・合成データ GREEN・code review Critical 8 + Warning 10 修正済み・CR-03 回帰も解消）
- [x] 評価指標と確率品質受入基準（Calibration / Brier / LogLoss / sum(p) 分布 / 安定性）— Validated in Phase 6: Evaluation & Calibration Gates（EVAL-01/02/03・evaluator.py 拡張 quantile_max_dev/ECE/MCE + check_acceptance_gate 構造的 BLOCK/hybrid WARN・compute_monotonicity/yearly_inversion・segment_eval 6軸 Plotly HTML+JSON・run_evaluation.py 統合 CLI・D-07 主モデル=**LightGBM** 確定（全指標で CatBoost 上回る）・gate verdict WARN（SC#2 達成・BLOCK 発火なし）・D-04 事前登録指標不変・REVIEW HIGH#8 部分証明の正直記録（Calibration では BL-1/BL-4 に劣る）・live DB is_primary lightgbm=true/22213行・verification passed 12/12）
- [x] Streamlit UI 画面（UI-01・レース一覧・p_fukusho_hit/EV/recommend_rank/fukusho_odds・再現性スタンプ inline・3タブ・read-only・§16.1除外）+ CSV出力（OUT-01 予測CSV 20列 / OUT-02 backtest CSV 16列・UTF-8 BOM+CRLF）— Validated in Phase 7: Presentation（UI-SPEC Sign-Off 6/6・checkpoint:human-verify で live-DB 3 bug 修正[sys.path/SQL引用符/deprecation]・CR-01 recovery_rate §11.6 effective_stake 口径修正・code review Warning 9 + Info 6 follow-up・tests/ui 56 passed・全 unit 444 passed・verification 36/36 must-haves）
- [x] リーク防止の対抗的（adversarial・注入型）監査テストスイート + フルスイート GREEN 証明 + 再現性スモーク統合（TEST-01・SC#1/#2/#3）— Validated in Phase 8: Adversarial Audit Suite（tests/audit/ に SC#2 の3ケース[lookahead/payout正欠損/fold race_id共有] + D-06 UI/CSV を注入型メタ検証として新設・KEIBA_SKIP_DB_TESTS unset で live-DB フルスイート 499 passed/1 skipped[Phase 6 C6 stale 既知]/failed 0・SC#3 合成層+live-DB CLI 層 bit-identical PASS・reports/08-audit.{md,json} でサーフェス別カバレッジ+Known Limitations honest 開示・verification 11/11 must-haves）
- [x] 相手強度（as-of `field_strength`）+ レース内相対特徴量（`speed_index_rank` 3軸 / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`）— Validated in Phase 10: Opponent Strength & Race-Relative Features（FEAT-02/FEAT-03・CYCLE-2 HIGH-C2-1 source-as-of full-pipeline 再計算で値レベル PIT 保証・competition ranking で同着/欠損境界明文化・SAFE-01 adversarial audit で AST odds/ninki proxy 0件 + lookahead 注入逆証明・byte-reproducible snapshot `20260626-1a-opponentstrength-v1` 106cols/554,267行・schema 0.6.0 で27新feature registry parity・SC#5 非劣化 gate PASS [Brier -0.00022(改善) / LogLoss +0.00487 / AUC +0.00180(改善)・全て D-16 許容幅内・同一 trainer B-3]・regression 574 passed・verification 5/5 must-haves・※ code review Critical 4件は周辺堅牢性で gap-closure 繰延）

### Active

**v1.0 shipped 2026-06-25**（Leak-Free Fukusho Pipeline・監査 passed・GAP-INT-01 解消）。出馬表確定後モデル（Phase 1-A）による `p_fukusho_hit` 算出・固定ルール仮想購入 backtest ともに Validated（Phase 4-6 で主モデル LightGBM 確定・Phase 5 で25 backtest 行レベル DB 永続化・返還/中止 honest 会計）。

**v1.1 Ability Feature v2 & Conditional Calibration — SHIPPED 2026-06-28。** 機構（FEAT/MODEL/EV/EVAL/SAFE）は全て完成（cross-phase 9/9 WIRED・BLOCKER 0・E2E live-DB byte-reproducible・Core Value 完全保持・監査 gaps_found は検証証跡補完と暫定数値の引き継ぎのみ）。Spike 001 ablation で成功仮説（追加特徴量で黒字化）がデータで否定: 黒字化したのは **Phase 9 基本6（speed figure・binary）のみ**（cross-window 5窓平均回収率1.14）・Phase 9.1 拡張/Phase 10 相手強度・レース内相対/Phase 11 race-relative は回収率を下げる。A1（Phase 9 基本6・label v1.1.0・binary）は is_primary=True でデプロイ済み（ユーザー承認・backtest 反映済み）。

- （v1.1 計画時）外部2AI リサーチ統合・過去人気/オッズ proxy 除外（市場回帰）・core value 再定式化（オッズ帯別条件付き calibration）は全て実行済み
- 正直な結論: 成功基準「市場残差能力の定量測定」は達成（falsification + ablation で測定）・「投票層過大予測是正」は race-relative でなく A1 binary で黒字化（マイルストーン成功仮説のデータによる否定・次マイルストーンで A1 精査）

### Out of Scope

<!-- 明確な境界。理由付きで再追加を防ぐ。要件定義書 3.3・7.3・2.1 準拠。 -->

- EveryDB2セットアップ / Parallels Desktop・Windows VM構築 — プロジェクト開始前にユーザー側で完了済み前提（3.1）
- Mac側PostgreSQLインストール・接続設定・テーブル作成 — EveryDB2側の責務、開始前完了前提（3.1）
- EveryDB2更新実行 / JRA-VAN Data Lab.契約・設定 — データ供給は完了済み前提（3.1）
- 実馬券購入・自動投票・自動購入ツール連携 — 本システムは利益を保証せず、安全性要件で明示的に除外（3.3, 19.3）
- Phase 1でのワイド・三連複モデル — Phase 2以降（3.3, 8.1）
- 障害競走・新馬戦・複勝発売なしレースのモデル対象化 — データ保存のみ、Phase 1モデルは除外（7.3）
- 海外競馬 — 開催体系・馬券種・オッズ形成・データ構造が異なるため（2.1）
- MLflow / Optuna導入 — Phase 1安定後に検討（21）

## v1.1 Shipped: Ability Feature v2 & Conditional Calibration（2026-06-28）

**Outcome:** 機構（FEAT-01/02/03・MODEL-01・EV-01・EVAL-01/02・SAFE-01）は全て完成（cross-phase 9/9 WIRED・BLOCKER 0・E2E live-DB byte-reproducible・Core Value 完全保持）。監査 gaps_found は BLOCKER 0・検証証跡補完（Phase 9/9.1 VERIFICATION 欠落）と暫定数値（Phase 11/12 は v1.0.0 universe・reopen 不可 guard）の引き継ぎのみ。Spike 001 ablation で成功仮説がデータで否定: 黒字化したのは Phase 9 基本6（speed figure・binary）のみ（cross-window 5窓平均1.14）・Phase 9.1 拡張/Phase 10/Phase 11 race-relative は回収率を下げる。A1（Phase 9 基本6・label v1.1.0・binary）は is_primary=True でデプロイ済み。

**Target features（P0）:**
- スピード指数（走破タイムの馬場/距離/トラック/クラス正規化・Beyer 的）
- 相手強度補正 + レース内相対特徴量（rank / gap_to_top / field_strength）
- レース内相対確率モデル（独立二値分類 → sum(p)=払戻対象数 制約・race-level top-k）
- `p_lower`（下側信頼限界）による EV 判定への移行（点推定 `p` の過信削減）
- 評価指標拡張（selected-only calibration / EV-decile-ROI / model-market disagreement-ROI / snapshot-final slippage）+ falsification test `logit(outcome) ~ logit(market) + logit(model)`

**Deferred（後続マイルストーン）:**
- P1: ペース・展開・調教タイム・騎手/調教師条件別 rolling・過去馬体重
- Phase 2（別モデル・当日情報）: 当日速報馬体重・当日馬場・直前オッズ（要件§13 PIT 再設計を要する）

## Context

**前提環境（プロジェクト開始前にユーザー側で完了済み）：** M2 Pro MacBook / Parallels Desktop上のWindows VM / EveryDB2 / Mac側PostgreSQL（Homebrew）。EveryDB2が JRA-VAN Data Lab. データを取得し、Mac側PostgreSQLへ直接保存・テーブル作成・2015年1月1日以降のデータ更新を完了済みであることを前提とする。

**データ：** 2015年1月1日以降のJRAデータを全件保存。2015〜2016年前半はfeature warm-up期間とし、学習・評価の主対象は2016年後半以降（特にバックテストは2019年夏季競馬以降を中心候補）。JRA平地競走（新馬戦以外、複勝発売対象、2歳未勝利以上）を初期モデル対象とする。

**設計思想：** 能力予測とEV計算を分離する。予測タイミング別にモデルを分け（Phase 1-Aは出馬表・馬番・枠番確定後）、未来情報リークを厳しく防ぐ（as-of管理・オッズ時点固定・当日情報不使用）。バックテストはrace_id単位かつ時系列順で、同一race_idのtrain/testまたぎを禁止する。DB・分析エンジンは過度に複雑化しない。

**v1.3の重要改訂点（実装時にブレやすい仕様）：** 複勝ラベルを最終出走頭数ではなく発売開始時点基準＋払戻テーブル優先に、オッズ時点固定で後知恵選択禁止、仮想購入ルールの明文化、as-of管理導入、クラス正規化は競走条件コード基準、推奨ランクはEV・確率・オッズ下限のみで初期定義、返還時 `effective_stake` と同着処理、市場ベースライン解釈、sum(p)分布チェック。

**プロジェクト名「v3」の由来：** 特別な意味はない通番（過去の失敗知見の引き継ぎではない）。

## Constraints

- **Tech stack**: Python 3.12（uv管理、問題時は3.11切替可）/ LightGBM・CatBoost・scikit-learn / PostgreSQL（主DB）/ DuckDB（大量集計・Parquet分析時のみ補助）/ Parquet（学習データセット）/ Streamlit（ローカル画面）/ Git — 要件定義書17.1
- **前提完了事項**: EveryDB2更新済み・Mac側PostgreSQL接続・テーブル作成済みであること（要件定義書3.1）。これら未完了の場合はPhase 1を開始できない
- **データ期間**: 2015年1月1日以降のJRAデータ（要件定義書6.1）
- **安全性**: 実馬券購入・自動投票は明確にスコープ外。推奨ランクは参考情報であり購入判断を強制しない（要件定義書19.3）
- **再現性**: モデルバージョン・特徴量スナップショット・ラベル定義バージョン・`odds_snapshot_policy`・`backtest_strategy_version` を保存し、同じ条件で再学習・再現できること（要件定義書19.1）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 主予測値を `p_fukusho_hit`（複勝払戻対象確率）とし、3着以内確率とは区別する | JRAの複勝発売・払戻ルールに基づく正確な定義が必要（要件1.1, 10.1） | — Pending |
| モデル特徴量に当日オッズを入れず、EV計算にのみ使用する | 能力予測と市場評価を分離し、リークを防ぐ（要件2.2, 9.3） | — Pending |
| 複勝ラベルは最終出走頭数ではなく、発売開始時点ベース＋払戻テーブル優先 | 発売開始後の取消・除外で誤判定するのを防ぐ（要件10.2-10.5） | — Pending |
| オッズ時点を固定（発走30分前/10分前）し、後知恵オッズ選択を禁止 | バックテストの再現性と過大評価防止（要件11.2） | — Pending |
| バックテストはrace_id単位・時系列順、train/testまたぎ禁止 | 評価の信頼性確保（要件8.4, 15.4） | — Pending |
| 競走中止は不的中として扱い、除外禁止 | 実運用の負けをバックテストから消して回収率を過大評価するのを防ぐ（要件10.6） | — Pending |
| PostgreSQLを主DBとし、DuckDBは補助分析のみ | 過度な複雑化を避ける（要件5.2, 12.1） | — Pending |
| 推奨ランクは未定義の予測信頼度を使わず、EV・確率・オッズ下限のみで初期定義 | Phase 1では信頼度が未成熟なため（要件11.5） | — Pending |
| core value を「`p` とオッズの独立性」でなく「オッズ帯別条件付き calibration（過大でないこと）」に再定式化 | 独立性は数学的に厳しすぎる（優秀なモデルほど `p` とオッズは負相関）・真正の要件は「投票層/EV帯で `p` が過大でないこと」（外部 ChatGPT/Codex 2AI リサーチ一致・要件§2.2/§9.3 整合） | — Pending |
| 過去人気/過去オッズ proxy 特徴量は導入しない | 過去市場評価の proxy は `p` を市場暗示確率に引きずらせ market edge を殺す（市場回帰）・debug + 外部2AI リサーチの一致結論 | — Pending |
| 回収率0.65天井の解決は Phase 1-B（オッズ特徴量）でなく、能力特徴量の精密化（スピード指数等）+ レース内相対確率モデルで図る | core value 維持での正統な改善道・Benter/Bolton&Chapman の fundamental model 実証例支持・市場回帰を避ける | ⚠️ Revisit: v1.1 で実行したが Spike 001 で成功仮説否定（Phase 9 基本6 のみ黒字・拡張特徴量/race-relative は回収率悪化） |
| 主モデル（is_primary）は Phase 9 基本6（speed figure・binary・label v1.1.0）= A1 | Spike 001 ablation で cross-window 5窓全て黒字（平均1.14・leak 再監査 GREEN）・「全部入り≠最善」「特徴量を引く方向」が新 universe で証明されたため | ✓ Good（A1 デプロイ済み・backtest 反映済み） |
| Phase 11/12 は reopen せず（guard C-12-02-1）・数値結果は label v1.0.0 universe 暫定 | 同一 model_version の rr 予測行を load_predictions で上書きすると Phase 12 が正しく計算した p_lower が静かに消える silent data corruption リスク・「落ちる」状態は安全装置 | ✓ Good（凍結維持・Spike 001 が v1.1.0 正準ベースライン） |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

**Milestone v1 — Phase progress:**

- **Phase 1: Trust & Foundation — Complete (2026-06-17).** Raw hybrid quality gate (verdict=pass) + normalized ETL（全 varchar 明示キャスト・staging-swap idempotent）+ class normalization（jyokencd5×gradecd×race_date 機械導出・コード連続性実証）+ リーク防止プリミティブ4種（pit_join / group_split / category_map / calibrator）を5層スキーマ上に bootstrap。raw read-only を REVOKE + raw_fingerprint md5 の二重保護で実証。76 テスト green・ruff clean。確定した基盤決定: psycopg3 pool + pydantic-settings 2ロール DSN、sklearn 1.9.0 は `cv='prefit'` 削除で `FrozenEstimator` prefit idiom 必須、`n_odds_tanpuku` が単複共用テーブル名（`n_odds_fukusho` は非存在）。Deferred debt: code review の Warning 9件（WR-02 トランザクション分離・WR-08 readonly_cur rollback 等・operational/infra・core value 非影響）。

- **Phase 2: Fukusho Labels — Complete (2026-06-18).** 複勝ラベル生成ETL（`src/etl/fukusho_label.py` 1080行・2層 raw/validated label・D-04 4値 `label_validation_status`・D-03 §7.2 `is_model_eligible`・REVIEWS HIGH #1-#7 対応）+ §10.5 払戻突合ゲート（`src/etl/label_reconcile.py` 886行・6検査 BLOCK/INFO・>99.9% agreement 実測 **100.0%**・4063 held-out races・NULL-safe NOT EXISTS + LPAD zero-pad・tautology 回避の独立 HR payout 再構築）+ `label_spec.yaml`（D-07 Git管理）+ label スキーマ GRANT 拡張（reader+etl・REVIEWS HIGH #3 PUBLIC 不使用）。実DB: `label.fukusho_label` 554,267行・idempotent（2回実行 checksum 完全一致）・raw 不変（D-06）。130 テスト green・TDD RED→GREEN（02-02→02-03、27テスト）。実行中の W5 checkpoint は「実DB接続可能」と判断し continuation で自律実行 → live DB のみ暴露される schema bug を計8件検出・修正。Deferred debt: code review BLOCKER 5件は verifier 評估で WARNING/NOT-A-BUG（CR-01 drift INFO化は Phase 8 監査強化・CR-02 SQL injection は psycopg3 パラメータ化推奨・CR-04 raw 偽正例は §10.3 が validated を学習目標に明示・Phase 8 監査）・`label.fukusho_label.race_date` 全行 NULL → Phase 3 で feature_cutoff 用に設定。

- **Phase 3: As-of Features & Snapshots — Complete (2026-06-19).** PIT-correct feature builder（rolling 6系統×3軸=18 + static + running_style・`merge_asof(direction='backward')` 相当の per-observation latest-K algorithm）+ 不変 versioned Parquet snapshot（§12.4 metadata・byte-reproducible）+ frozen category map（`__UNSEEN__`/`__MISSING__` sentinel・training-window-only fit）。5 plans（03-01〜04 + gap-closure 03-05）。03-05 で CR-01（silent-empty rolling 6列 timediff/babacd 削除 + 3者 registry parity + end-to-end regression guard）・WR-01（estimated_running_style PIT pre-filter・look-ahead leak 解消）・CR-02（JOIN 両側 project_window_filter）・CR-03（race_date 欠損 fail-loud）・CR-04（joblib/pickle → JSON・ACE 解消）を閉鎖。live snapshot v2: 554,267行 × 55列・SHA256 一致・CR-01 parity 実証（登録列 0列が 100% null）。191 テスト green。verification passed 4/4 must-haves。Deferred debt: code re-review の advisory 4件（CR-01-new manifest→persist 順序依存・WR-01' silent no-filter fallback・WR-02 _fetch except→空DF・WR-03 rolling groupby().apply pandas 3.x 非推奨）は現 SC 非破壊だが Phase 4 学習開始前 hardening を強く推奨 → **Phase 3.1 で完了**（下記）。

- **Phase 3.1: Timediff/Babacd Rolling Restoration — Complete (2026-06-19).** Phase 3 gap-closure（03-05）で silent-empty breach 対策として一時削除した `rolling_timediff_*` / `rolling_babacd_*` 計6 feature を、registry↔rolling↔availability↔Parquet の4者 parity を維持したまま復元。4 plans: (1) normalized ETL 拡張（`timediff` varchar4 + baba3 `sibababacd`/`dirtbabacd`/`trackcd`・raw pass-through・staging-swap DDL 駆動化）・(2) `run_feature_build.py` persist→exists assert→manifest 順序化（CR-01新）・(3) `builder.py`（timediff real parse・babacd trackcd 分岐派生・WR-01'/WR-02 fail-loud）+ `rolling.py` 8系統化（×4軸=32列・WR-03 count vector化）+ availability/yaml 3者 parity + `label_spec` sentinel 0000・(4) live-DB snapshot rebuild。当初の完了時点では feature_count=63 の中間 snapshot で実証したが、**Phase 4 入力の正は D-01 で `20260620-1a-postreview-v2`（feature_count=62・fa_version 0.3.0・SHA256 `26c685f0…ecbdd2`・`byte_reproducible_scope=parquet_data_only_metadata_excluded`）に確定**。feature 63→62 は CR-02 で `rolling_jyocd_mean_5`→`mode_5`(rename) + `rolling_jyocd_sd_5`(remove)（commit 43bd81f・jyocd はカテゴリカル値で mean/sd は無意味・§13.4 odds-free allowlist 違反なし・D-02 で研究者が git+実データで確定）。rolling 6 feature non-null（timediff 89.0%/babacd 57.6%）・registry↔Parquet parity・raw 不変（raw_touched=False・public 前後不変）・216 tests green。Phase 3 の code review advisory 4件 hardening 完了。verification passed 9/9 must-haves。Phase 4 Model & Prediction は postreview-v2 stamped snapshot を唯一の入力として学習・推論可能（§19.1 再現性＝聖域 遵守）。

- **Phase 4: Model & Prediction — Complete (2026-06-20).** leak-free・bit-identical な `p_fukusho_hit` pipeline を確立。LightGBM 4.6.0（native categorical・非負 code・`__MISSING__`/`__UNSEEN__` sentinel・`num_threads=1`・target/mean encoding 構造的禁止 §14.3）+ CatBoost 1.2.10（`cat_features` + `has_time=True`・`race_start_datetime`-sorted Pool・`thread_count=1`・高基数 `_code` 列 cat_features 化 HIGH#6/MODL-03）。`orchestrator.py`（HIGH#12 循環依存解消）+ `run_train_predict.py` E2E・`prediction.fukusho_prediction` に両モデル各 22,213 行（model_version-scoped swap HIGH#1・2回実行 idempotent checksum bit-identical）。6 plans（04-01..06）順次実行。**SC#1** Parquet-only 学習（DB由来0）・**SC#3** leak diagnostic（対抗的構造証明・target encoding 実呼出0件・`.cat.codes.min()>=0` fail-loud）・**SC#4** bit-identical（`FIXED_REPRODUCE_TS` + 固定 thread/seed・両モデル `np.array_equal` 実データ実証）達成。**SC#2 は正直に「部分証明」**: 主モデルは Brier/LogLoss/AUC で baselines 上回るが・D-04 gold-standard **Calibration** で BL-1(0.001426)/BL-4(0.044928)に劣る → Phase 6 ゲートで最終判定（review HIGH#8・ユーザー指示通り Phase-4 ブロッカーでない）。`KEIBA_SKIP_DB_TESTS` unset で 262 tests green / 0 skipped（green-by-skip 防止 HIGH#10）。**Deferred to Phase 6**: BL-2/BL-3 市場データ NaN（test split で ninki/fukuoddslow 取得不可）・BL-4/BL-5 キャリブレーション（`calibrate_bl4_bl5=False`・BL_UNCALIBRATED_NOTE）。**Deferred to Phase 8**: SC#3 live-data 証明（本 Phase は合成データの対抗的構造診断）。feature snapshot 入力: `20260620-1a-postreview-v2`（feature_count=62）。verification passed 4/4 must-haves。

---
- **Phase 6: Evaluation & Calibration Gates — Complete (2026-06-23).** 確率品質受入基準の評価・キャリブ指標・segment 安定性・主モデル確定を一本化。evaluator.py 拡張（D-05 quantile_max_dev/ECE/MCE 純 NumPy bit-identical・check_acceptance_gate D-01/D-02 構造的 BLOCK[baselines全敗 AND sum(p)著乖離] / D-03 曖昧 WARN[Spearman・反転数] hybrid gate・compute_monotonicity_warn・compute_yearly_inversion_warn）・**D-04 事前登録指標（calibration_max_dev 等）は一切不変**（T-04-24 後知恵すり替え防止）。segment_eval.py 新規（6軸 year/month/jyocd/entry_count/ninki/odds_band・REVIEW HIGH#4 banding 関数・Plotly 静的 HTML[include_plotlyjs='directory' 共有] + JSON）。is_primary DB migration（3ファイル連鎖・REVIEW HIGH#7 0行 RuntimeError post-condition・HIGH#8 NOT NULL DEFAULT false・set_primary_model idempotent）。run_evaluation.py 統合 CLI（EVAL-01/02/03・reports/06-evaluation.{md,json} + reports/06-segments/・byte-reproducible JSON・REVIEW HIGH#5 sum_p_measurement・HIGH#6 BLOCK 時 report 残存・RFC 8259 strict JSON[NaN→null]）。**D-07 主モデル = LightGBM 確定**（brier=0.15222/logloss=0.47488/auc=0.73230/calib=0.231/monotonicity=1.0/backtest回収率=0.7022 の全指標で CatBoost 上回る・D-08 tiebreak=backtest_recovery_rate）→ live DB is_primary lightgbm=true/22213行・catboost=false/22213行（両モデル保持）。**gate verdict = WARN（SC#2 達成: baselines_all_lose=False・BLOCK 発火なし）**。**REVIEW HIGH#8 正直「部分証明」**: 主モデルは Brier/LogLoss/AUC で BL-1/4/5 全てに勝るが・D-04 gold-standard **Calibration** では BL-1(0.001426)/BL-4(0.044928)に劣る（LightGBM=0.231）→ reports/06-evaluation.{md,json} と ROADMAP で隠されず記録。sum(p) threshold=0.30 は現データに厳しすぎる（violation 71%・threshold_appropriate=False）→ WARN 記録のみで SC#2 通過・閾値調整は別途検討。verification passed 12/12（gap closure: hit_rate 集約追加[SC#1/EVAL-01] + NaN→null 厳格 JSON 化）。

- **Phase 7: Presentation — Complete (2026-06-24).** read-only Streamlit UI + CSV 出力で予測/EV/推奨/backtest を確認可能に。3 plans（07-01 基盤[DRY列定数/jyocdマップ/テーマ/Wave0テスト]・07-02 loaders+CLI[BLOCKER-1 正経路: odds/EV/rank は JODDS snapshot + compute_ev_and_rank 再計算・OUT-01/02 CLI UTF-8 BOM+CRLF]・07-03 UI 本体[app.py + prediction/backtest/calibration 3タブ・selection_mode 正引数・SC#1 6数値列 %.3f・再現性スタンプ5項目 inline・honest 注記・§16.1除外・Plotly D-05]）。UI-SPEC Sign-Off 6/6。**checkpoint:human-verify（live-DB）で unit test 検出不可の 3 bug 修正**: app.py sys.path ガード（0e46b7e・ModuleNotFoundError）・loaders EV_lower/upper 引用符（ef83b1e・UndefinedColumn）・use_container_width→width="stretch"（db97a1f・2025-12-31 削除予定日経過）。code review CR-01 Critical（backtest_tab recovery_rate を §11.6 effective_stake 分母に・5b2273c）修正・Warning 9 + Info 6 は follow-up。memory phase7-ui-live-db-bugs 記録（live-DB 必須 bug パターン・unit test KEIBA_SKIP_DB_TESTS では検出不可）。tests/ui 56 passed・全 unit 444 passed・ruff clean・verification 36/36 must-haves（human_needed 2件は checkpoint 済み・07-UAT.md resolved）。

- **Phase 8: Adversarial Audit Suite — Complete (2026-06-25).** v1 マイルストーン最終フェーズ・TEST-01（リーク防止の対抗的監査テストを含む）の出荷ゲート確立。3 plans（08-01 tests/audit/ adversarial 4ファイル[SC#2 3ケース+D-06 UI/CSV]・08-02 scripts/run_reproducibility_smoke.py + src/audit/report.py + reports/08-audit.{md,json}・08-03 checkpoint:human-verify で live-DB フルスイート GREEN 証明）。**SC#1** フルスイート 499 passed / 1 skipped（test_evaluator.py:490・Phase 6 C6 stale・非 KEIBA_SKIP_DB_TESTS 由来）/ failed 0・KEIBA_SKIP_DB_TESTS unset で requires_db 全実行（conftest fail-by-default policy 確証）。**SC#2** tests/audit/ 9テスト GREEN（lookahead/payout正欠損/fold race_id共有 の注入型メタ検証 + D-06 AST read-only 保証/再現性スタンプ欠落検出・5段階鋳型・docstring cross-reference）。**SC#3** 合成層（run_reproducibility_smoke.py・calibrator bit-identical + tests/audit/）+ live-DB CLI 層（run_train_predict/run_backtest --check-reproduce・bit-identical PASS）両 GREEN。reports/08-audit.{md,json}：サーフェス別カバレッジマップ（SC#1 8サーフェス+evaluation_metrics）+ SC#1/#2/#3 対応表 + Known Limitations 3項目（回収率天井 ~0.65・Calibration BL 劣位・odds JODDS 再検証 subject）の honest 開示・byte-reproducible。verification passed 11/11 must-haves。**留意点（ギャップではない）**: 1 skipped は Phase 6 C6 stale（Plan 06-05 委譲）・label.fukusho_label.race_date の3度目の再発を run_label_race_date_backfill.py で都度復元（idempotent・raw 不変・554267 non-NULL）して SC#3 backtest を GREEN 化・根本調査は別 /gsd-debug 推奨。memory fukusho-recovery-070-structural-ceiling 整合。

*Last updated: 2026-06-28 after **v1.1 milestone shipped**（Ability Feature v2 & Conditional Calibration・機構完成・成功仮説はデータで否定 → A1=Phase 9 基本6 を is_primary にデプロイ・backtest 反映済み）。v1.0/v1.1 詳細は .planning/milestones/ 参照*
