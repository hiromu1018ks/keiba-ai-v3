# Roadmap: Keiba AI v3

## Overview

**v1.0 shipped 2026-06-25** — leakage-critical・reproducibility-critical な odds-free 複勝 `p_fukusho_hit` pipeline。各出走馬の複勝払戻対象確率を推定し、固定オッズ時点のEVで評価、race_id単位・時系列順の再現可能バックテストで定量評価、read-only Streamlit UI + CSV で提示。コアバリュー（リーク防止・再現性）は完全保持。

回収率0.65-0.70天井は odds-free 1-A モデルの構造的限界（3層構造: 市場情報不足→中高オッズ域過大予測→EV演算増幅→複勝控除率天井）。要件未達でなく正直な結論。

**v1.1 shipped 2026-06-28** — core value（odds-free）を維持したまま能力特徴量を「速度（スピード指数）・相手強度・レース内相対」へ拡張し、レース内相対確率モデル（`sum(p)=払戻対象数` 制約）と `p_lower` EV 判定・falsification test を実装した。**機構（FEAT/MODEL/EV/EVAL/SAFE）は全て完成し cross-phase 9/9 WIRED・E2E pipeline が live-DB で byte-reproducible・Core Value（リーク防止・再現性）は完全保持**（監査 gaps_found は検証証跡の補完と暫定数値の引き継ぎ・BLOCKER 0）。ただし Spike 001 ablation で**マイルストーン成功仮説（追加特徴量で黒字化）がデータで否定された**: 追加特徴量（Phase 9.1 拡張・Phase 10 相手強度/レース内相対）と race-relative モデルは回収率を下げ、黒字化したのは **Phase 9 基本6（speed figure・binary）のみ**（cross-window 5窓平均回収率1.14・leak 再監査 GREEN）。A1（Phase 9 基本6・label v1.1.0・binary）は is_primary=True でデプロイ済み（ユーザー承認・backtest 反映済み）。

詳細は `.planning/milestones/v1.0-ROADMAP.md`・`v1.1-ROADMAP.md`（フル Phase Details）・各 `*-MILESTONE-AUDIT.md`（監査）。

## Milestones

- ✅ **v1.0 Leak-Free Fukusho Pipeline** — Phases 1-8 + 3.1 (shipped 2026-06-25)
- ✅ **v1.1 Ability Feature v2 & Conditional Calibration** — Phases 9-12 (shipped 2026-06-28)

## Phases

<details>
<summary>✅ v1.0 Leak-Free Fukusho Pipeline (Phases 1-8 + 3.1) — SHIPPED 2026-06-25</summary>

- [x] Phase 1: Trust & Foundation (4/4 plans) — completed 2026-06-17
- [x] Phase 2: Fukusho Labels (4/4 plans) — completed 2026-06-18
- [x] Phase 3: As-of Features & Snapshots (5/5 plans) — completed 2026-06-19
- [x] Phase 3.1: Timediff/Babacd Rolling Restoration (4/4 plans, INSERTED) — completed 2026-06-19
- [x] Phase 4: Model & Prediction (6/6 plans) — completed 2026-06-20
- [x] Phase 5: EV & Backtest (6/6 plans) — completed 2026-06-21
- [x] Phase 6: Evaluation & Calibration Gates (5/5 plans) — completed 2026-06-23
- [x] Phase 7: Presentation (3/3 plans) — completed 2026-06-24
- [x] Phase 8: Adversarial Audit Suite (3/3 plans) — completed 2026-06-25

</details>

<details>
<summary>✅ v1.1 Ability Feature v2 & Conditional Calibration (Phases 9-12) — SHIPPED 2026-06-28</summary>

**機構完成（cross-phase 9/9 WIRED・BLOCKER 0・E2E live-DB byte-reproducible）・成功仮説はデータで否定（Phase 9 基本6 のみ黒字）・A1 デプロイ済み。**

- [x] **Phase 9: Speed Figure Foundation** — 走破タイムを馬場/距離/トラック/クラス補正したスピード指数（Beyer 的）を odds-free・PIT-correct に構築 (5/5 plans・completed 2026-06-25) [FEAT-01]
- [x] **Phase 9.1: Speed Ability Profile Expansion (INSERTED)** — Phase 9 の speed_figure 6→17 feature 拡張 (1/1 plan・completed 2026-06-26) [FEAT-01 拡張・⚠ Spike 001 で回収率悪化主因（分布形状5）と判定]
- [x] **Phase 10: Opponent Strength & Race-Relative Features** — 相手強度（as-of）とレース内相対特徴量を odds-free・PIT-safe に追加 (9/9 plans・completed 2026-06-26) [FEAT-02/03・⚠ Spike 001 で回収率寄与ほぼなし]
- [x] **Phase 11: Race-Relative Probability Model** — 独立二値分類から `sum(p)=払戻対象数` 制約・race-level 補正のレース内相対確率モデルへ移行 (5/5 plans・completed 2026-06-27) [MODEL-01・機構完成・数値結果は v1.0.0 universe 暫定・回収率寄与 v1.1.0 非証明・is_primary=f]
- [x] **Phase 12: p_lower EV & Falsification Evaluation** — `p_lower` 下側信頼限界によるEV判定へ移行し、評価指標拡張と falsification test で market residual を統計検証 (5/5 plans・completed 2026-06-28) [EV-01/EVAL-01/EVAL-02/SAFE-01・機構完成・数値結果は v1.0.0 universe 暫定]

**Spike 001 ablation（VALIDATED・新 universe v1.1.0）の結論**: A1（Phase 9 基本6・binary）が黒字化の正解（cross-window 5窓平均1.14・leak 再監査 GREEN）。「全部入り≠最善」「特徴量を引く方向」が証明された。Phase 9.1 拡張・Phase 10 相手強度/レース内相対・Phase 11 race-relative は全て回収率を下げる。A1 は is_primary=True でデプロイ済み。詳細は `reports/12-evaluation/ablation-results.md`・`.planning/spikes/001-ablation-recovery/`。

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Trust & Foundation | v1.0 | 4/4 | Complete | 2026-06-17 |
| 2. Fukusho Labels | v1.0 | 4/4 | Complete | 2026-06-18 |
| 3. As-of Features & Snapshots | v1.0 | 5/5 | Complete | 2026-06-19 |
| 3.1. Timediff/Babacd (INSERTED) | v1.0 | 4/4 | Complete | 2026-06-19 |
| 4. Model & Prediction | v1.0 | 6/6 | Complete | 2026-06-20 |
| 5. EV & Backtest | v1.0 | 6/6 | Complete | 2026-06-21 |
| 6. Evaluation & Calibration Gates | v1.0 | 5/5 | Complete | 2026-06-23 |
| 7. Presentation | v1.0 | 3/3 | Complete | 2026-06-24 |
| 8. Adversarial Audit Suite | v1.0 | 3/3 | Complete | 2026-06-25 |
| 9. Speed Figure Foundation | v1.1 | 5/5 | Complete | 2026-06-25 |
| 9.1. Speed Ability Profile Expansion (INSERTED) | v1.1 | 1/1 | Complete | 2026-06-26 |
| 10. Opponent Strength & Race-Relative Features | v1.1 | 9/9 | Complete | 2026-06-26 |
| 11. Race-Relative Probability Model | v1.1 | 5/5 | Complete | 2026-06-27 |
| 12. p_lower EV & Falsification Evaluation | v1.1 | 5/5 | Complete | 2026-06-28 |
