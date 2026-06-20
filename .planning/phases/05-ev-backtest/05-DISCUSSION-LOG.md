# Phase 5: EV & Backtest - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 5-EV & Backtest
**Areas discussed:** オッズ時点ポリシー, BT窓と再学習ループ, BL-3投資ROI比較, 返還・中止会計の正

---

## オッズ時点ポリシー（時点選択ルール含む）

| Option | Description | Selected |
|--------|-------------|----------|
| 確定オッズで完結（推奨） | `odds_snapshot_policy='confirmed_final'`（n_odds_tanpuku確定値）を事前登録固定ポリシーに。発走前時点(30/10分前)はJODDS未取り込みのため将来延期 | |
| JODDS取り込みで30/10分前再現 | EveryDB2の時系列オッズ(JODDS)蓄積を有効化。ただし過去レース再取得はJRA-VAN配信制約で不可の懸念 | |
| 確定完結+JODDS並行調査 | 確定で安全に完結しつつJODDS可能性を並行調査 | |

**User's choice:** （自由記述）「単複の時系列オッズは取得可能です。今取得を開始したので確認してみて。」
**Notes:** ユーザーが JODDS 取得を開始（過去遡取可能と判断）。実DB確認で `n_jodds_tanpuku` 48,432行（2015年・分単位粒度・`DataKubun` 1中間が主）を確認 → **JODDS 採用**で確定。当初「過去再取得不可」の懸念は覆った。STATE.md blocker（odds-snapshot timing granularity）解消。

### 時点選択ルール（発走-N分丁度のスナップショットが無い場合）

| Option | Description | Selected |
|--------|-------------|----------|
| 過去最近接を採用（推奨） | 発走時刻-N分「以下」の直近 HappyoTime（未来リーク構造的に不可・§13 PIT と整合）。当該時刻以前に1件も無ければ no_bet | ✓（委任） |
| 許容誤差以内のみ | 発走-N分±数分以内のみ使用、範囲外は no_bet | |
| Claude裁量で設計 | §11.2/§11.3 + PIT 原則で研究者/計画者が設計 | |

**User's choice:** （自由記述）「それぞれの選択肢の意味がわからない。」→ 平易に再説明後、「はい。それでいいです」
**Notes:** 技術設計詳細すぎたと判断。平易に再説明（過去最近接＝未来を覗かない安全設計）の上、Claude 裁量（Core Value 準拠）で固定。特殊値（`----`/`****`/`0000`/`0999`）も no_bet。

---

## BT窓と再学習ループ

| Option | Description | Selected |
|--------|-------------|----------|
| 要件の全候補を比較 | §15.5 の BT-1..5 × 発走30/10分前 × LightGBM/CatBoost（約20通り）。各BT窓で学習期間を変えて再学習。Core Value完全履行 | ✓ |
| 代表窓で比較 | 代表BT窓×両policy×両モデル。単独報告禁止は維持しつつ計算量抑制。フル行列は将来拡張 | |
| お任せ | Core Valueと§15.5を踏まえ最適規模を設計 | |

**User's choice:** 要件の全候補を比較
**Notes:** Phase 4 予測は val 2024 後半のみ（test 2023/2025 未予測）のため、各 BT窓で再学習して test 予渓を再生成する。固定 snapshot（`postreview-v2`）から race_date filter。

---

## BL-3 投資ROI比較

| Option | Description | Selected |
|--------|-------------|----------|
| 比較する（推奨） | Phase 4 引き継ぎ履行。BL-3（人気順）で固定ルール仮想購入→回収率を主モデルと比較。「市場人気戦略 vs AI穴馬志向」のhonest対比 | ✓ |
| 将来延期 | Phase 5は主モデル2つのBT行列に集中。BL-3はPhase 4の確率品質ベンチマークに留める | |
| お任せ | Phase 4 D-07の意図とCore Valueを踏まえ判断 | |

**User's choice:** 比較する（推奨）
**Notes:** Phase 4 D-07 で「Phase 5」と明記済み。BL-3 は p=1/odds で EV 自己参照(=1.0)になるため、選択は EV でなく人気順等で行う（Claude 裁量）。

---

## 返還・中止会計の正

| Option | Description | Selected |
|--------|-------------|----------|
| お任せ（推奨） | §11.6 + JRAルール + label/n_harai データ経路で設計。対抗的テストで各シナリオ stake/payout を assert | ✓ |
| 不成立・特別払戻を個別議論 | FuseirituFlag2/TokubaraiFlag2/PayFukusyoPay を実データ踏まえて個別に詰める | |

**User's choice:** お任せ（推奨）
**Notes:** 会計ルールは§11.6 で確定（取消/除外=返還 effective_stake=0・競走中止=loss effective_stake=100）。実データは `label.fukusho_label`（取消/除外/中止フラグ）+ `n_harai`（HenkanFlag2/FuseirituFlag2/TokubaraiFlag2/PayFukusyoPay）の直接読みで再現。

---

## Claude's Discretion

- **時点選択ルール（D-02）:** backward 最近接（ユーザー委任・Core Value 準拠）
- **返還・中止会計のデータ経路設計（D-05）:** §11.6 + JRAルール + label/n_harai（ユーザー「お任せ」）
- **BT窓定義の厳密適用・category_map の BT窓再 fit・calib slice carve:** §15.5 + Phase 3/4 契約に従い研究者/計画者が設計
- **EV/rank/仮想購入ルール実装・backtest DB永続化設計・reports慣例・タイブレーク等:** 要件 §11 に従い Claude 裁量

## Deferred Ideas

- Phase 6（評価ゲート・主モデル確定）・Phase 7（Streamlit/CSV）・Phase 8（対抗的監査）は後続フェーズ
- 発走前オッズの更なる時点比較（60分前/5分前/締切直前 等・§11.2 将来候補）は Phase 5 では 30/10分前の2本に留める
- `phase3-advisory-hardening.md`（todo score 0.6・Phase 3.1 完了済み）は無関係のため fold せず
