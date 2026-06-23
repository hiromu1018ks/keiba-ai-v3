# Phase 6: Evaluation & Calibration Gates - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-23
**Phase:** 6-Evaluation & Calibration Gates
**Areas discussed:** 受入ゲートの厳格さ, キャリブ指標の再設計, 主モデル確定と運用, セグメント別安定性の成果物

---

## 受入ゲートの厳格さ（EVAL-02 / §15.2・Core Value 直結）

### Q1: §15.2 確率品質受入基準を BLOCK にするか WARN 止めにするか

| Option | Description | Selected |
|--------|-------------|----------|
| 構造的BLOCKのみ（推奨） | モデル破綻（baselines 全敗・sum(p) 著乖離）のみ hard fail。それ以外は WARN。hybrid gate（Phase1 D-01/Phase2 D-02）の延長 | ✓ |
| WARNのみ（全基準参考） | §15.2 全て WARN。出荷停止は Phase 8 リーク/再現性ゲートのみ | |
| §15.2 全基準 BLOCK | 全受入基準を通過必須。曖昧基準の機械化リスク大 | |

**User's choice:** 構造的BLOCKのみ（推奨）
**Notes:** Core Value「リーク防止と再現性だけは守る」に整合。確率品質は改善指標。

### Q2: 構造的 BLOCK（hard fail）の対象範囲

| Option | Description | Selected |
|--------|-------------|----------|
| baselines全敗+sum(p)著乖離（推奨） | 順序付け能力ゼロ + 確率スケール破綻の両方を安全網 | ✓ |
| baselines 全敗のみ | SC#2 の本質（AI 付加価値ゼロ）のみ BLOCK。sum(p) は WARN | |
| BLOCK 設けない | 全て WARN。Phase 8 のみ聖域 | |

**User's choice:** baselines全敗+sum(p)著乖離（推奨）

### Q3: 曖昧基準（年次反転・bin単調性）の機械判定厳格度

| Option | Description | Selected |
|--------|-------------|----------|
| 参考レポート・数値併記（推奨） | 反転数・単調違反 bin 数・Spearman 等を数値で出すが判定は人間。過機械化回避 | ✓ |
| 緩い閾値で WARN | 明白な異常のみ WARN | |
| 厳格閾値で WARN | 客観的閾値（Spearman > 0.9 等）で WARN。境界で偽陽性リスク | |

**User's choice:** 参考レポート・数値併記（推奨）

---

## キャリブ指標の再設計（debug calib-maxdev-vs-baselines の Phase 6 領域）

### Q1: 事前登録指標 calibration_max_dev（uniform・ガードなし）の扱い

| Option | Description | Selected |
|--------|-------------|----------|
| 事前登録維持+新指標併記（推奨） | uniform max_dev（事前登録・不変）を温存し quantile/ECE/MCE を補助追加。T-04-24 完全回避 | ✓ |
| Phase 6 で指標再登録 | Phase 4 事前登録を破棄し Phase 6 で再登録。連続性が切れる | |
| uniform max_dev のみ継続 | 指標追加なし。構造バイアスは注記のみ | |

**User's choice:** 事前登録維持+新指標併記（推奨）

### Q2: Phase 6 で追加するキャリブ指標

| Option | Description | Selected |
|--------|-------------|----------|
| quantile max_dev + ECE（推奨） | quantile bin（BL-1 bin 退化バイアス解除）max_dev + ECE（robust） | |
| quantile + ECE + MCE | 上記に MCE（worst-case）も追加。網羅的 | ✓ |
| ECE のみ | 単一 robust 指標でシンプル | |

**User's choice:** quantile + ECE + MCE
**Notes:** 網羅性を優先。max_dev（bin別）+ ECE（重み付け平均）+ MCE（worst-case）の3視点。

### Q3: 高確率域（pred>0.7）過信の対処範囲

| Option | Description | Selected |
|--------|-------------|----------|
| 可視化・記録のみ（推奨） | 根本対処は Optuna 導入（将来）に委ねる。Phase 4 bit-identical 維持 | ✓ |
| キャリブ方法を再調整 | isotonic clip/sigmoid 併用/calib slice 拡大を Phase 6 で試す。再現性再検証コスト | |
| 両方 | 可視化しつつ限定的にキャリブ再調整も | |

**User's choice:** 可視化・記録のみ（推奨）

---

## 主モデル確定と運用（Phase 4 D-03/D-04 事前登録基準の実体化）

### Q1: LightGBM vs CatBoost の選定方式

| Option | Description | Selected |
|--------|-------------|----------|
| 人間判断・記録（推奨） | 全指標を並列提示し D-04 基準で人間が決定・理由記録。過機械化回避 | ✓ |
| 段階的フィルタ | Calibration 閾値→Brier→AUC の順で機械選定。閾値に恣意性 | |
| スコアリング関数 | 指標の重み付け合計で順位付け。重み設定が新たな論点 | |

**User's choice:** 人間判断・記録（推奨）

### Q2: 僅差・同点時の扱い

| Option | Description | Selected |
|--------|-------------|----------|
| タイブレークで1つ（推奨） | 固定優先順位（backtest 回収率→計算コスト低=LightGBM）で1つ選ぶ | ✓ |
| 両方主モデルとして残す | 僅差なら両方を is_primary。運用複雑 | |
| ケースバイケースで人間判断 | レポートを見て個別決定 | |

**User's choice:** タイブレークで1つ（推奨）

### Q3: 主モデル確定の記録形態

| Option | Description | Selected |
|--------|-------------|----------|
| is_primary フラグ付与（推奨） | prediction テーブルに is_primary=true/false。両モデル行保持。Phase 7 は is_primary で表示 | ✓ |
| 主モデル version のみ記録 | レポート/STATE に version 記録。テーブル不変 | |
| 主モデル行のみ残す | 未選定モデル行を削除/除外。再現性・比較可能性を損なう | |

**User's choice:** is_primary フラグ付与（推奨）

---

## セグメント別安定性の成果物（EVAL-03 / §15.3）

### Q1: segment 別 calibration curve の成果物形態

| Option | Description | Selected |
|--------|-------------|----------|
| JSON + Plotly HTML（推奨） | 機械可読 JSON + Plotly 静的 HTML。Phase 7 Streamlit は JSON を動的描画。CLAUDE.md Plotly 推奨に整合 | ✓ |
| JSON データのみ | データ生成のみ・描画は Phase 7 に委ねる | |
| matplotlib PNG | 静的画像。Streamlit 動的性を活かせない | |

**User's choice:** JSON + Plotly HTML（推奨）

### Q2: segment 間の比較・可視化方法

| Option | Description | Selected |
|--------|-------------|----------|
| curve 並列 + scalar 表（推奨） | segment ごと curve 重ね描き + ECE/MCE/max_dev の segment 表。collapse 一目可視化 | ✓ |
| scalar 表のみ | ECE/MCE/max_dev の segment 別表。局所パターン見えにくい | |
| curve のみ | 並列 curve のみ。数値比較しにくい | |

**User's choice:** curve 並列 + scalar 表（推奨）

### Q3: 6軸（year/month/競馬場/頭数/人気帯/オッズ帯）の生成範囲

| Option | Description | Selected |
|--------|-------------|----------|
| 全6軸生成（推奨） | EVAL-03 完全履行。計算量・肥大は受容（segment 評価は軽量） | ✓ |
| 優先3軸に絞る | year/競馬場/人気帯 等に絞る。残りは将来 | |
| 全6軸scalar+優先軸curve | scalar は全6軸・curve 描画は優先軸のみ | |

**User's choice:** 全6軸生成（推奨）

---

## Claude's Discretion

- **構造的 BLOCK 閾値の具体値**（D-02）— baselines 全敗の定義（全 baselines vs BL-1 のみ・LogLoss/Brier 両方か一方か）と sum(p) 著乖離の閾値（±X%・large/small バケット別）を §15.2 と実データ分布で確定
- **新キャリブ指標の実装詳細**（D-05）— bin 数・MIN_BIN_COUNT・実装箇所（evaluator.py 拡張 vs 新モジュール）・純 NumPy bit-identical 実装
- **タイブレーク規則の具体化**（D-08）— 固定優先順位の決定的順序
- **統合評価経路の設計** — `scripts/run_evaluation.py`（仮）CLI で統合するか既存 run_* に追加するか
- **reports/06-evaluation.{md,json} 慣例** — 04-eval/05-backtest パターン踏襲・`reports/06-segments/` 構成
- **segment 評価モジュールの配置** — `src/model/segment_eval.py`（仮）等
- **Plotly HTML のレイアウト** — curve 重ね描きの軸/凡例/色分け・scalar 表の併記形式
- **テスト構成（§17.3）** — ゲート判定ロジックの単体テスト・segment 評価 contract テスト・bit-identical 回帰テスト
- **`is_primary` フラグの DB スキーマ影響**（D-09）— prediction テーブルへの列追加・NULL 許容・DEFAULT false・既存行 backfill・GRANT・CHECK 制約

## Deferred Ideas

- **Phase 7（Presentation）:** Streamlit 動的 calibration curve 描画・`is_primary=true` 主モデル表示・OUT-01/02 CSV 出力。Phase 6 は JSON+Plotly HTML データ生成まで
- **Phase 8（Adversarial Audit）:** 受入ゲート判定ロジックの対抗的監査・`is_primary` 後知恵すり替え検出・segment 評価の PIT 正当性（TEST-01）
- **高確率域過信の根本対処（将来 Optuna 導入時）:** isotonic clip/sigmoid 併用/calib slice 拡大/特徴量見直し。Phase 6 は可視化のみ
- **キャリブ指標の更なる拡張（将来）:** bin 数チューニング・segment 別 ECE 重み付け最適化・Platt scaling 比較
