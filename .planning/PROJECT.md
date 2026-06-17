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

### Active

<!-- 現在のスコープ。要件定義書の Phase 1 を中心とする。すべて出荷検証まで仮説。 -->

- [ ] 複勝ラベル `fukusho_hit` の生成と払戻テーブル突合（発売開始時点ベース、`sales_start_entry_count` 取得・復元含む）
- [ ] as-of特徴量管理（`as_of_datetime` / `feature_cutoff_datetime` / `feature_availability` によるリーク防止）
- [ ] 出馬表・馬番・枠番確定後モデル（Phase 1-A）による `p_fukusho_hit` 算出
- [ ] 複勝EV計算（`EV_lower` / `EV_upper`）と推奨ランク算出
- [ ] 固定ルール仮想購入バックテスト（race_id単位・時系列順、返還・競走中止の扱いを含む回収率再現）
- [ ] 評価指標と確率品質受入基準（Calibration / Brier / LogLoss / sum(p) 分布 / 安定性）
- [ ] Streamlit最小画面（レース一覧・p_fukusho_hit・オッズ・EV・推奨ランク・スナップショット情報）
- [ ] CSV出力（予測CSV・バックテストCSV）

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

---
*Last updated: 2026-06-17 after Phase 1 complete*
