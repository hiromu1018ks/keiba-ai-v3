# Requirements: Keiba AI v3

**Defined:** 2026-06-25
**Milestone:** v1.1 Ability Feature v2 & Conditional Calibration
**Core Value:** オッズ非依存の確率 `p_fukusho_hit` と固定オッズ時点のEVで、過小評価されている馬の複勝払戻対象入り可能性をリークなく検出し、race_id単位・時系列順の再現可能なバックテストで定量評価できること。リーク防止と再現性だけは必ず守る。

## v1.1 Requirements

回収率0.65天井（debug `fukusho-recovery-070` ROOT CAUSE・3層構造: 市場情報不足→中高オッズ域過大予測→EV演算増幅→複勝控除率天井）へ core value（odds-free）を維持したまま正統に対応する。能力特徴量を「着順中心」から「速度・相手強度・レース内相対」へ拡張し、投票層の過大予測を是正・回収率向上余地を測る。同時に falsification test で「odds-free で market residual が残るか」を検証する（特徴量不足 vs 構造的限界の鑑別）。

各要件は外部2AI（ChatGPT/Codex）リサーチの P0 一致項目（`.planning/research/v1.1-domain-analysis.md`）に基づく。core value 再定式化（独立性→オッズ帯別条件付き calibration）・過去人気/オッズ proxy 除外（市場回帰）を遵守。

### 特徴量（FEAT）

- [x] **FEAT-01**: スピード指数を構築する — 走破タイムを距離/馬場/クラス/トラック/開催日で補正した能力値（Beyer 的）。着順でなく能力を直接測る主軸。素材（`time`/`kyori`/`babacd`/`trackcd`/`class_code_normalized`）は normalized 層に存在確認済み（品質・正式カラム名は計画フェーズで精査）。
- [ ] **FEAT-02**: 相手強度補正特徴量を追加する — 過去走の相手の as-of 能力平均・`field_strength` で、低着順でも強い相手なら価値があることを反映（odds-free・PIT-safe）。
- [ ] **FEAT-03**: レース内相対特徴量を追加する — スピード指数等の出走馬内 `rank` / `gap_to_top` / `gap_to_3rd` / `field_strength_adjusted_rank`（複勝は相対競争・各馬独立事象でない）。

### モデル設計（MODEL）

- [ ] **MODEL-01**: レース内相対確率モデルを導入する — 独立二値分類から `sum(p)=払戻対象数(2/3)` 制約・race-level top-k calibration（Plackett-Luce/Harville 的）へ近づけ、過大EVを構造的に抑える。

### EV判定（EV）

- [ ] **EV-01**: EV 判定を点推定 `p` から `p_lower`（下側信頼限界・bootstrap/ensemble/conformal）へ移行する — 点推定 `p` の過信を削り投票層の過大p を減らす（過学習聖域厳守・train/calib で設計）。

### 評価（EVAL）

- [ ] **EVAL-01**: 評価指標を拡張する — selected-only calibration / EV-decile 別実現 ROI / model-market disagreement 別 ROI / odds snapshot→final payout slippage を追加（全体 Brier が隠す投票層の失敗を可視化・§15.2 事前登録指標は不変）。
- [ ] **EVAL-02**: falsification test を導入する — `logit(outcome) ~ logit(market_implied) + logit(model_p)` を時系列 out-of-sample で測り、odds-free market residual が統計的に残るかを検証。回収率0.65が特徴量不足か構造的限界かを鑑別（market 情報は診断層のみ・`p` モデルには入れない）。

### 聖域（SAFE）

- [x] **SAFE-01**: core value を維持する — オッズ/人気/過去人気/過去オッズ proxy は `p` モデル特徴量に入れない（市場回帰で edge 消滅・2AI 一致）。オッズ帯別条件付き calibration を受入基準に追加し、投票層での過大予測を構造的に検出する。

## Future Requirements（後続マイルストーン）

### P1 特徴量精緻化（次マイルストーン候補）

- ペース・展開予測（逃げ馬数・先行圧力・前後半ラップ）
- 調教タイム・追い切り評価（坂路・ウッド）
- 騎手・調教師の条件別 rolling 成績（target leakage 注意）
- 距離延長/短縮・surface change 適性
- 種牡馬・母父の条件別適性（Bayesian smoothing 必須）
- 過去馬体重（当日速報は Phase 2）

### Phase 2（当日情報・別モデル・要件§13 PIT 再設計を要する）

- 当日速報馬体重・馬体重増減
- 当日馬場・天候
- 発走直前オッズ・票数変動（EV/selector 層のみで利用・`p` モデルには入れない）

## Out of Scope

| Feature | Reason |
|---------|--------|
| 過去人気・過去オッズ proxy の `p` モデル特徴量化 | 過去市場評価の proxy は `p` を市場暗示確率に引きずらせ market edge を殺す（市場回帰）・debug + 外部2AI リサーチ一致・core value（§2.2/§9.3）違反 |
| 当日オッズ・直前オッズの `p` モデル特徴量化 | `p` が市場確率へ回帰し過小評価検出と混同・core value 違反（Phase 3 で EV/selector 層のみ検証可） |
| Dr. Z 型 win-pool→複勝価格裁定 | 市場プール構造を使う価格裁定・odds-free `p` モデルと相性不良（診断用には有用だが本マイルストーン外） |
| 実馬券購入・自動投票 | 要件§3.3/§19.3 で明示的にスコープ外 |
| test 窓での閾値/戦略事後選択 | debug で閾値枯悦確定（~0.67天井）・過学習聖域違反（§11.2） |
| Wide/三連複モデル | 要件 Phase 2/3・本マイルストーンは複勝 1-A 枠内改善に集中 |

## Traceability

ロードマップ作成時に gsd-roadmapper が埋める。

SAFE-01（core value 維持・横断要件）は全フェーズで遵守すべき聖域だが、特に Phase 9/10（特徴量追加・リーク/市場回帰ガード）・Phase 11（モデル変更・リーク/市場回帰ガード）・Phase 12（オッズ帯別条件付き calibration 受入基準）に明示マッピング。

| Requirement | Phase | Status |
|-------------|-------|--------|
| FEAT-01 | Phase 9 | Complete |
| FEAT-02 | Phase 10 | Pending |
| FEAT-03 | Phase 10 | Pending |
| MODEL-01 | Phase 11 | Pending |
| EV-01 | Phase 12 | Pending |
| EVAL-01 | Phase 12 | Pending |
| EVAL-02 | Phase 12 | Pending |
| SAFE-01 | Phase 9 / 10 / 11 / 12 (横断・各 SC に明示) | Complete |

**Coverage:**

- v1.1 requirements: 8 total
- Mapped to phases: 8/8 ✓
- Unmapped: 0 ✓

**Phase マッピング根拠（依存関係 DAG）:**

- Phase 9 (FEAT-01): スピード指数は能力特徴量の基盤 → FEAT-02/03 の前提
- Phase 10 (FEAT-02 + FEAT-03): 相手強度とレース内相対は FEAT-01 に依存 → 同フェーズで追加（複雑度 fine 粒度で自然な境界）
- Phase 11 (MODEL-01): FEAT-01/02/03 完成後に入力。レース内相対確率モデル
- Phase 12 (EV-01 + EVAL-01 + EVAL-02): MODEL-01 の `p` 完成後。p_lower EV 移行・評価拡張・falsification は最終フェーズで統合（§15.2 事前登録指標不変の上に追加指標を載せる）

---
*Requirements defined: 2026-06-25 after v1.1 milestone start（外部 ChatGPT/Codex 2AI リサーチ統合・debug ROOT CAUSE 準拠）*
*Last updated: 2026-06-25 after ROADMAP creation (8/8 mapped・Phase 9-12)*
