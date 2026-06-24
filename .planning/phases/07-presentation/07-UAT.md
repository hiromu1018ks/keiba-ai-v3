---
status: resolved
phase: 07-presentation
source: [07-VERIFICATION.md]
started: 2026-06-24T20:30:00Z
updated: 2026-06-24T20:30:00Z
---

## Current Test

number: 1
name: ライブ DB 接続での Streamlit UI 描画（レース選択→各馬6数値+再現性スタンプ展開）
expected: 実DB環境で `streamlit run src/ui/app.py` を起動し・予測一覧タブでレース選択→各馬の p_fukusho_hit/EV/fukusho_odds/recommend_rank（%.3f）と再現性スタンプ5項目が展開される
awaiting: none（resolved）

## Tests

### 1. ライブ DB 接続での Streamlit UI 描画
expected: 実DB環境で `streamlit run src/ui/app.py` を起動し・予測一覧タブでレース選択→各馬の p_fukusho_hit/EV/fukusho_odds/recommend_rank（%.3f）と再現性スタンプ5項目が展開される
result: pass — 07-03 Task 3 checkpoint:human-verify で実施（ユーザー実ブラウザ確認・approved）。起動時 ModuleNotFoundError（commit 0e46b7e 修正）・backtest UndefinedColumn（ef83b1e 修正）・use_container_width deprecation（db97a1f 修正）を経て「いい感じでしたよ」承認。CR-01 recovery_rate 口径（5b2273c 修正）も Phase 5 §11.6 整合を live-DB で確認（recovery_rate=1.5）。

### 2. Segment Calibration タブ Plotly 描画
expected: 6軸（year/month/jyocd/entry_count/ninki/odds_band）selectbox 切替で Plotly calibration curve がインタラクティブ描画・幅 stretch レンダリング・scalar 指標表表示
result: pass — 07-03 Task 3 checkpoint:human-verify で実施（ユーザー実ブラウザ確認・approved）。load_segment_json 全6軸 live-DB/ファイル検証 OK（dict・len=2）。width="stretch" で deprecation 解消（db97a1f）。

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

(none — 2件とも 07-03 checkpoint:human-verify で確認済み。本 UAT は gsd-verifier の human_needed（ライブブラウザ描画振る舞い・grep/AST で見えない分）を記録整理したもの。自動検証可能な truth は全て VERIFIED・07-VERIFICATION.md 36/36 must-haves)
