# Roadmap: Keiba AI v3

## Overview

**v1.0 shipped 2026-06-25** — leakage-critical・reproducibility-critical な odds-free 複勝 `p_fukusho_hit` pipeline。各出走馬の複勝払戻対象確率を推定し、固定オッズ時点のEVで評価、race_id単位・時系列順の再現可能バックテストで定量評価、read-only Streamlit UI + CSV で提示。コアバリュー（リーク防止・再現性）は完全保持。

回収率0.65-0.70天井は odds-free 1-A モデルの構造的限界（3層構造: 市場情報不足→中高オッズ域過大予測→EV演算増幅→複勝控除率天井）。要件未達でなく正直な結論。戦略判断（A受容/B 1-A改善/C Phase 1-B）は次マイルストーンで扱う。

詳細は `.planning/milestones/v1.0-ROADMAP.md`（フル Phase Details）・`v1.0-MILESTONE-AUDIT.md`（監査）。

## Milestones

- ✅ **v1.0 Leak-Free Fukusho Pipeline** — Phases 1-8 + 3.1 (shipped 2026-06-25)

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

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Trust & Foundation | v1.0 | 4/4 | Complete | 2026-06-17 |
| 2. Fukusho Labels | v1.0 | 4/4 | Complete | 2026-06-18 |
| 3. As-of Features & Snapshots | v1.0 | 5/5 | Complete | 2026-06-19 |
| 3.1 Timediff/Babacd (INSERTED) | v1.0 | 4/4 | Complete | 2026-06-19 |
| 4. Model & Prediction | v1.0 | 6/6 | Complete | 2026-06-20 |
| 5. EV & Backtest | v1.0 | 6/6 | Complete | 2026-06-21 |
| 6. Evaluation & Calibration Gates | v1.0 | 5/5 | Complete | 2026-06-23 |
| 7. Presentation | v1.0 | 3/3 | Complete | 2026-06-24 |
| 8. Adversarial Audit Suite | v1.0 | 3/3 | Complete | 2026-06-25 |
