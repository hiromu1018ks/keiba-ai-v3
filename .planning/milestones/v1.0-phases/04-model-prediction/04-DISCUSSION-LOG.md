# Phase 4: Model & Prediction - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 4-Model & Prediction
**Areas discussed:** 入力 snapshot の確定, 主モデルと下流への引き渡し, prediction 成果物の永続化, BL-3 複勝オッズ逆数ベースラインの扱い

---

## Area 1: 入力 snapshot の確定

| Option | Description | Selected |
|--------|-------------|----------|
| postreview-v2 を正とする | 本日の直列化bug修正+schema 0.3.0 を取り込んだ最新版を Phase 4 入力の正とする。PROJECT.md/STATE.md の v3 参照はドリフト（Phase 4 で文書修正推奨）。provenance の snapshot_id stamp もこれに統一。 | ✓ |
| v3 を正とする | PROJECT.md/STATE.md 記載の v3(63・fa0.2.0)。直列化bug修正未取り込みで Phase 8 監査の SHA256 scope 不整合リスク。 | |
| 両方で比較 | 両 snapshot で学習し比較。hash 二重管理・feature scope 不整合で複雑化。 | |

**User's choice:** postreview-v2 を正とする
**Notes:** §19.1 再現性＝聖域。postreview-v2（62 feature・fa 0.3.0・SHA256 scope=parquet_data_only_metadata_excluded）が本日 commit 92e1310/ef635b6/e5a75e2 の修正取り込み済みの最新。PROJECT.md/STATE.md の v3 参照は Phase 4 で修正。

| Option | Description | Selected |
|--------|-------------|----------|
| 研究者が実データ+gitで確定 | feature_availability.yaml git diff(0.2.0→0.3.0) + 両 Parquet カラム diff で 63→62 の差を特定。odds-free allowlist 違反がないか検証。 | ✓ |
| ユーザー既知（自由記入） | 差を自由記述で提示。 | |
| You decide | Claude/研究者に一任。 | |

**User's choice:** 研究者が実データ+gitで確定
**Notes:** feature 63→62 の差は研究者が git + 実データで確定し、odds-free allowlist 違反がないことを検証してから Phase 4 feature 仕様を固定。

---

## Area 2: 主モデルと下流への引き渡し

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 まで確定しない | Phase 4 は両モデル学習+キャリブレーション+比較表。主モデル確定は Phase 6 評価ゲート（選定基準は Phase 4 で事前登録・後知恵回避）。Phase 5 は両モデル backtest。 | ✓ |
| Phase 4 で主モデル1つ確定 | 事前登録基準で1つ確定し Phase 5 は1モデル。もう一方は artifact 保持。 | |
| LightGBM をデフォルト | 両モデル学習+比較のみ・Phase 5 開始時に LightGBM をデフォルト・Phase 6 で見直し。 | |

**User's choice:** Phase 6 まで確定しない
**Notes:** 最も厳格。選定基準を結果を見る前に事前登録し後知恵回避。Phase 5 の 2x workload 受容。

| Option | Description | Selected |
|--------|-------------|----------|
| Calibration 重視 | 信頼性曲線・sum(p) 分布適合・Brier の calibration 成分を最優先。EV 整合性=Core Value に直結。 | ✓ |
| LogLoss 重視 | 全体的な予測品質（calibration+判別力の統合）。 | |
| Brier Score 重視 | MSE 型・解釈しやすい。 | |
| 複合スコア | Calibration + sum(p) + LogLoss の重み付け（重みも Phase 4 で固定）。 | |

**User's choice:** Calibration 重視
**Notes:** 事前登録。判別力は次点。具体的な重み/閾値は Phase 4 計画で固定。

---

## Area 3: prediction 成果物の永続化

| Option | Description | Selected |
|--------|-------------|----------|
| prediction DB テーブル | 予測を prediction DB テーブル（provenance 列付き・staging-swap idempotent）。モデル artifact は models/ ファイル。5層スキーマ意図（feature=不変Parquet・prediction/backtest=queryable Postgres）に合致。 | ✓ |
| 予測も Parquet のみ | Phase 3 D-08 踏襲・最シンプル・manifest+hash で再現性。prediction 層は未使用。 | |
| hybrid（Parquet正+DBミラー） | 予測は Parquet が正・Phase 7 直前で prediction DB を query 用ミラー作成。作業量最大。 | |

**User's choice:** prediction DB テーブル
**Notes:** feature=不変 Parquet（学習入力）・prediction/backtest=queryable Postgres（結果層）の分離が 5層スキーマの意図する読み。Phase 7 Streamlit が SQL 照会。ETL ロール GRANT 拡張必要。

| Option | Description | Selected |
|--------|-------------|----------|
| ネイティブ形式 | LightGBM booster.save_model・CatBoost save_model・calibrator joblib。バージョン安定・ポータブル。Phase 3 pickle-ACE 回避思想を適用。 | ✓ |
| joblib/pickle 統一 | 全モデル・キャリブレータを joblib/pickle。バージョン非互換リスク・pickle 排除流れと逆行。 | |
| You decide | Claude/研究者に一任。 | |

**User's choice:** ネイティブ形式
**Notes:** models/{model_version}/ 配下。.gitignore 対象。§19.1 再現性は code + uv.lock + snapshot + provenance。

---

## Area 4: BL-3 複勝オッズ逆数ベースラインの扱い

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 4 で BL-1..5 全部 | BL-3 は確定複勝オッズ逆数(正規化)を市場暗示確率ベンチマークとして LogLoss/Brier/Calibration 比較に使用（§14.2 同一情報条件でない旨明記・モデル特徴量に混入しない・リークなし）。BL-2 は確定人気。SC#2 比較表を Phase 4 で完成。betting ROI 比較は Phase 5。 | ✓ |
| BL-2/3 は Phase 5 に延期 | Phase 4 は BL-1/4/5（odds 不要）のみ。比較表は BL-3 なし（SC#2 部分充足）。境界は最も clean。 | |
| BL-3 を30/10分前snapshotで | odds 読込 pipeline を Phase 4 で構築（Phase 5 再用）。BACK-04 両報告原則に準拠。 | |

**User's choice:** Phase 4 で BL-1..5 全部
**Notes:** 確率品質ベンチマークとしての BL-3 は betting の odds_snapshot_policy(Phase 5) と別物。後知恵リークなし（BL-3 はモデルに影響しない独立ベンチマーク）。SC#2 を完全充足。

| Option | Description | Selected |
|--------|-------------|----------|
| 確定オッズ/確定人気 | 市場コンセンサス最終値を BL-2/BL-3 の源泉とする。確率品質ベンチマークの標準。歴史レースに存在。 | ✓ |
| 発走N分前 snapshot | Phase 5 BACK-04 の固定 snapshot と一致するが Phase 5 方針決定に依存。 | |
| You decide | Claude/研究者に一任。 | |

**User's choice:** 確定オッズ/確定人気
**Notes:** n_odds_tanpuku（単複共用）の確定複勝オッズ・n_uma_race 系の確定人気（Ninki）。

---

## Claude's Discretion

- **train→calib→test の 3way 時系列分割設計** — calib slice の切り出し（manifest は train 2016-07〜2023/val 2024 のみ定義・calib sample <1000 件の sigmoid 切替含む）
- **低基数コードの categorical vs numeric 扱い** — jyocd/trackcd/sexcd/course_kubun/class_code_normalized（高基数 ID は category_map で確定）
- **early stopping 用 eval set のリーク防止設計**
- **SC#3 leak diagnostic の設計** — rare category 収縮テスト（target encoding 非混入の実証）
- **SC#4 reproduce smoke test の設計** — 固定 seed → bit-identical 予測の検証
- **ハイパーパラメータ初期値** — 手動（§21 MLflow/Optuna defer）
- **model_version 採番方式** — feature_snapshot_id と整合・両モデルを model_type で区別

## Deferred Ideas

- **Phase 5:** EV 計算・推奨ランク・race_id-grouped 仮想購入シミュレータ（固定 odds_snapshot_policy）・BT-1..5・BL-3 betting ROI 比較
- **Phase 6:** 確率品質受入基準ゲート・主モデル確定（D-03/D-04 事前登録基準）
- **Phase 7:** Streamlit 予測表示・prediction テーブル SQL 照会・予測/backtest CSV 出力
- **Phase 8:** SC#3/SC#4/race_id 分離/categorical-missing handling の対抗的監査（TEST-01）
- **Optuna ハイパラ最適化（将来）:** 評価/特徴量安定後に再評価
