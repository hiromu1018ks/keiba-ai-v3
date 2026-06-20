# Requirements: Keiba AI v3

**Defined:** 2026-06-16
**Core Value:** オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性をリークなく検出し、race_id単位・時系列順の再現可能なバックテストで定量評価できること。

> v1 は要件定義書 `docs/keiba_ai_requirements_v1.3.md` の **Phase 1「複勝」** に相当する。要件定義書が正。本ファイルと要件に乖離がある場合は要件定義書を優先する。

## v1 Requirements

複勝（fukusho）を主軸とした Phase 1 実装検証スコープ。各要件は要件定義書の該当節と `research/` 成果に基づく。

### データ基盤 (DATA)

- [x] **DATA-01**: EveryDB2由来PostgreSQLデータに対する品質チェックを実行し、主要テーブルの存在・件数・日付範囲・2015年以降の存在・主要項目のNULL・主キー/自然キーの重複・文字化け・コード値異常をレポートできる
- [x] **DATA-02**: normalized層のETLが型変換・コード変換を行い、原本テーブル（raw）を直接加工せずに別テーブルとして正規化データを生成できる
- [x] **DATA-03**: クラス正規化が文字列ではなく競走条件コード基準で行われ、`class_code_normalized`/`class_name_normalized`/`class_level_numeric`/`post_2019_class_system_flag` 等を保持できる

### 複勝ラベル (LABEL)

- [x] **LABEL-01**: 着順由来の一次ラベル `fukusho_hit_raw` と、払戻テーブル突合後の確定ラベル `fukusho_hit_validated` を生成できる
- [x] **LABEL-02**: `sales_start_entry_count` を取得でき、直接項目がなければ出馬表確定時点の出走予定馬と取消/競走除外の発表時刻から復元でき、復元不能な場合は `label_validation_status = unresolved` として学習/評価対象から除外できる
- [x] **LABEL-03**: `fukusho_hit_validated` が払戻テーブル上の複勝払戻対象馬と整合し、突合検査（対象馬の存在/過不足・同着・取消除外馬の誤正例・中止馬の扱い・複勝発売なし混入）の結果を `label_validation_status` として保存できる
- [x] **LABEL-04**: 同着時は払戻テーブルに存在する全複勝対象馬を正例とし、出走取消/競走除外は予測対象外（仮想購入時は返還）、競走中止は原則学習に含めて不的中として扱える

### 特徴量・as-of (FEAT)

- [x] **FEAT-01**: 各特徴量に `as_of_datetime`/`feature_cutoff_datetime`/`feature_snapshot_id`/`feature_availability`（`available_from_timing`/`leakage_risk_level` を含む）を付与し、point-in-time 正確性を保証して未来情報リークを防止できる
- [x] **FEAT-02**: Phase 1-A の特徴量を、当日馬場/天候/馬体重/当日オッズ/人気集中度/レース後通過順・上がり・走破タイム/当日レース結果由来集計 を除外して生成できる

### モデル・予測 (MODL)

- [x] **MODL-01**: 出馬表・馬番・枠番確定後に利用可能なデータのみで `p_fukusho_hit` を推定する Phase 1-A モデルを学習・予測できる（当日オッズを特徴量に使わない）
- [x] **MODL-02**: ベースラインモデル BL-1（頭数別一定）〜BL-5（LightGBM最小特徴量）を評価し、AIモデルが単純モデル/市場情報に対して付加価値を持つかを比較できる
- [x] **MODL-03**: LightGBM/CatBoost の時系列安全なカテゴリ・欠損処理（target encoding禁止・負値コード回避・欠損理由の区別・CatBoost `has_time`/LightGBMネイティブカテゴリ）を実装できる

### EV・推奨ランク (EV)

- [x] **EV-01**: `p_fukusho_hit` と複勝オッズ下限/上限から `EV_lower = p × odds_lower` / `EV_upper = p × odds_upper` を算出できる
- [x] **EV-02**: EV・確率・オッズ下限のみで推奨ランク（S/EV≥1.20, A/EV≥1.10, B/EV≥1.05, C/EV≥1.00, D/その他）を初期定義どおりに算出できる（未定義の予測信頼度は使わない）

### バックテスト (BACK)

- [x] **BACK-01**: バックテストを `race_id`単位かつ `race_date`/`race_start_datetime` 昇順で分割し、同一 `race_id` の train/test またぎを禁止（`race_id`-grouped time-series split）できる
- [x] **BACK-02**: 固定ルール（EV_lower≥1.05, p≥0.15, odds_lower≥1.5, 同一レース上位2頭, 1候補100円, 複勝のみ）で仮想購入を再現できる
- [x] **BACK-03**: 返還時 `effective_stake`=0・競走中止は `effective_stake`=100 として、回収率/損益/最大ドローダウン/selected_count/effective_bet_count/refund_count を `backtest_strategy_version` 付きで再現可能に計算できる
- [x] **BACK-04**: バックテスト意思決定オッズ時点を固定（`odds_snapshot_policy`、発走30分前/10分前固定）し、レース後の有利オッズ選択・最終オッズ無条件使用・欠損時都合の良い時点への差し替えを禁止できる

### 評価・品質 (EVAL)

- [ ] **EVAL-01**: 複勝的中率/回収率/損益/最大ドローダウン/購入点数/Brier Score/LogLoss/Calibration Curve を算出できる
- [ ] **EVAL-02**: 確率品質受入基準（年別Calibrationの極端逆転なし・bin実測率の単調増加・LogLoss/Brierのベースライン超過・`sum(p)`平均の理論値適合・中央値/SD/p10/p90）を検証できる
- [ ] **EVAL-03**: 年/月/競馬場/頭数/人気帯/オッズ帯 別の安定性と、全体/各軸の Calibration Curve を評価できる

### 画面 (UI)

- [ ] **UI-01**: Streamlit画面でレース一覧・各馬 `p_fukusho_hit`・複勝オッズ下限/上限・`EV_lower`/`EV_upper`・推奨ランク・`odds_snapshot_policy`/`odds_snapshot_at`・`model_version`・`feature_snapshot_id`・`backtest_strategy_version` を表示できる（ワイド/荒れ指数/コメント生成は表示しない）

### CSV出力 (OUT)

- [ ] **OUT-01**: 予測CSV（race_id/race_date/race_start_datetime/競馬場/レース番号/horse_id/horse_name/枠番/馬番/p_fukusho_hit/オッズ下限上限/EV/推奨ランク/スナップショット情報）を出力できる
- [ ] **OUT-02**: バックテストCSV（backtest_id/戦略バージョン/学習検証期間/odds_snapshot_policy/race_id/horse_id/selected_flag/stake/refund_flag/payout_amount/profit/fukusho_hit_validated/推奨ランク/EV）を出力できる

### テスト (TEST)

- [ ] **TEST-01**: 複勝ラベル生成・払戻テーブル突合・出走取消/競走除外/競走中止の扱い・オッズ時点固定・仮想購入ルール・`feature_cutoff_datetime`・評価指標計算・`race_id`単位分割・クラス正規化・カテゴリ/欠損処理 に対するテストを実装できる（リーク防止の対抗的監査テストを含む）

## v2 Requirements

要件定義書の Phase 2/3 相当。追跡のみで、現在のロードマップには含めない。

### ワイド・複勝拡張 (PHASE2)

- **PHASE2-01**: 開催日朝モデル（当日朝の天候/馬場状態を追加）
- **PHASE2-02**: 馬体重発表後モデル（馬体重/増減を追加）
- **PHASE2-03**: ワイド候補ペア抽出とワイド期待値（2頭の同時複勝対象確率）
- **PHASE2-04**: 予測信頼度の定義（分散・校正誤差・データ欠損率・類似サンプル数）
- **PHASE2-05**: Calibration改善とStreamlit表示拡張（ワイド候補/期待値/荒れ指数）

### 発走直前・三連複 (PHASE3)

- **PHASE3-01**: 発走直前オッズ対応・時系列オッズ/票数変化特徴量
- **PHASE3-02**: オッズ依存の市場補正モデル
- **PHASE3-03**: 三連複期待値モデル（組み合わせ爆発に注意）
- **PHASE3-04**: Streamlit高度化・モデル自動更新

### 運用基盤 (OPS)

- **OPS-01**: MLflow導入（Phase 1安定後）
- **OPS-02**: Optuna導入（特徴量/評価安定後）

## Out of Scope

明示的除外。スコープクリープを防ぐため理由を記載。要件定義書 3.3/7.3/2.1/21 準拠。

| Feature | Reason |
|---------|--------|
| 実馬券購入・自動投票・自動購入ツール連携 | 利益を保証せず、安全性要件で明示的に除外（3.3, 19.3） |
| 海外競馬 | 開催体系/馬券種/オッズ形成/控除率/データ構造/馬場クラス体系が異なる（2.1） |
| 障害競走・新馬戦のモデル対象化 | データ保存のみ、Phase 1モデルは除外（7.3） |
| 複勝発売なしレースのモデル対象化 | ラベル生成/払戻突合の対象外（7.3） |
| EveryDB2セットアップ/Parallels・Windows VM構築 | プロジェクト開始前にユーザー側完了前提（3.1） |
| Mac側PostgreSQLインストール/接続設定/テーブル作成 | EveryDB2側の責務、開始前完了前提（3.1） |
| EveryDB2更新実行/JRA-VAN Data Lab.契約・設定 | データ供給は完了済み前提（3.1） |
| Phase 1でのワイド/三連複モデル実装 | Phase 2/3（3.3, 8.1） |
| 後知恵オッズ時点選択 | バックテスト過大評価になるため禁止（11.2, 15.4） |
| 競走中止のバックテスト除外 | 実運用の負けを消して回収率を過大評価するため禁止（10.6） |

## Traceability

ロードマップ（`.planning/ROADMAP.md`）の8フェーズに全v1要件をマッピング済み。ビルド順DAG（raw品質ゲート → normalized ETL → ラベル生成 → as-of特徴量・スナップショット → モデル → 予測 → EV・バックテスト → 評価 → 画面/CSV → 対抗的監査テスト）に従う。各リーククリティカル層の境界は検証ゲート。

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1: Trust & Foundation | Complete |
| DATA-02 | Phase 1: Trust & Foundation | Complete |
| DATA-03 | Phase 1: Trust & Foundation | Complete |
| LABEL-01 | Phase 2: Fukusho Labels | Complete |
| LABEL-02 | Phase 2: Fukusho Labels | Complete |
| LABEL-03 | Phase 2: Fukusho Labels | Complete |
| LABEL-04 | Phase 2: Fukusho Labels | Complete |
| FEAT-01 | Phase 3: As-of Features & Snapshots | Complete |
| FEAT-02 | Phase 3: As-of Features & Snapshots | Complete |
| MODL-01 | Phase 4: Model & Prediction | In Progress (基盤 + data/calibrator/artifact 完了・学習/予測は後続 wave 03-06) |
| MODL-02 | Phase 4: Model & Prediction | Complete |
| MODL-03 | Phase 4: Model & Prediction | In Progress (data API + calibrator prefit wrapper 完了・LightGBM/CatBoost 本体は wave 03) |
| EV-01 | Phase 5: EV & Backtest | Complete |
| EV-02 | Phase 5: EV & Backtest | Complete |
| BACK-01 | Phase 5: EV & Backtest | Complete |
| BACK-02 | Phase 5: EV & Backtest | Complete |
| BACK-03 | Phase 5: EV & Backtest | Complete |
| BACK-04 | Phase 5: EV & Backtest | Complete |
| EVAL-01 | Phase 6: Evaluation & Calibration Gates | Pending |
| EVAL-02 | Phase 6: Evaluation & Calibration Gates | Pending |
| EVAL-03 | Phase 6: Evaluation & Calibration Gates | Pending |
| UI-01 | Phase 7: Presentation | Pending |
| OUT-01 | Phase 7: Presentation | Pending |
| OUT-02 | Phase 7: Presentation | Pending |
| TEST-01 | Phase 8: Adversarial Audit Suite | Pending |

**Coverage:**

- v1 requirements: 25 total
- Mapped to phases: 25 (fully mapped)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-16*
*Last updated: 2026-06-16 after roadmap creation — traceability populated*
