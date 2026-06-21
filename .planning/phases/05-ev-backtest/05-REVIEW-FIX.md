---
phase: 05-ev-backtest
fixed_at: 2026-06-21T00:00:00Z
review_path: .planning/phases/05-ev-backtest/05-REVIEW.md
iteration: 1
findings_in_scope: 20
fixed: 18
skipped: 2
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-06-21
**Source review:** `.planning/phases/05-ev-backtest/05-REVIEW.md`
**Iteration:** 1
**Scope:** critical_warning (Critical 8 + Warning 12 = 20 findings)

**Summary:**
- Findings in scope: 20 (Critical 8 + Warning 12)
- Fixed: 18 (Critical 8 + Warning 10)
- Skipped: 2 (Warning 2 = WR-10, WR-12)

## Verification Environment

- ユニットテスト (`tests/ev` 53件): **全件 pass** を修正毎に確認
- 並列の E2E テスト (`tests/ev/test_run_backtest_e2e.py` 14件) は pre-existing の
  `FileNotFoundError: snapshots/feature_matrix_20260620-1a-postreview-v2.parquet`
  (snapshot parquet 本体が無く manifest のみ配置) で全て fail 中。
  これは reviewer 指摘事項とは別の pre-existing 環境問題で・本 fix の対象外。
  修正前後で fail 件数は不変 (11 fail / 3 pass) で・回帰無しを確認済み。
- `tests/model/test_orchestrator*.py` / `tests/model/test_data.py` も同一原因で
  collection 時に fail (pre-existing)。
- ruff: 修正ファイル全体で B905 / E712 は pre-existing のみ・新規違反無し。

## Fixed Issues (Critical)

### CR-01: fetch_jodds の race_key 形式が他の全テーブルと不整合

**Files modified:** `src/ev/odds_snapshot.py`, `scripts/run_backtest.py`
**Commit:** `28e3091`
**Applied fix:** `fetch_jodds` と `_fetch_harai_race_level` の race_key 構築を
`make_race_key` 正準形式 (5要素・monthday 無し) に統一。monthday は SELECT 列に残し
happyo_datetime 計算用に保持。実データでオッズ全件 NaN 化する silent failure を解消。

### CR-02: load_labels 戻り値に race_key 列が無いのに merge で要求 (KeyError)

**Files modified:** `scripts/run_backtest.py`
**Commit:** `67dc536`
**Applied fix:** `_run_pipeline` の readonly_cursor block 直後で・label_df に
`make_race_key` で正準 race_key を付与してから後続の merge に渡す。

### CR-03: select_bets が label 由来列を要求するが label merge 前に呼ばれる (KeyError)

**Files modified:** `scripts/run_backtest.py`
**Commit:** `f87b617` (CR-06 と同一コミット)
**Applied fix:** merge 順序を「snapshot merge → HARAI merge → label merge →
compute_ev_and_rank → select_bets」に入れ替え。compute_ev_and_rank は
p_fukusho_hit / fuku_odds_lower/upper のみ消費し label 系列に非依存のため
EV 計算の正確性は保たれる (deep cross-file 検証済み)。
**Status:** fixed: requires human verification (merge 順序入れ替え・logic 変更)

### CR-04: 実データ BL-3 market_df に race_date 列が無いのに compute_backtest_metrics が sort で使用 (KeyError)

**Files modified:** `scripts/run_backtest.py`
**Commit:** `66ab31f`
**Applied fix:** `_run_pipeline` で market_df に `make_race_key` で race_key を付与し・
label_df から `is_fukusho_sale_available` を (race_key 単位・many_to_one) で補完。
`_run_bl3_backtest` で full_candidate に label_df から `race_date` を (race_key 単位) で補完。
**Status:** fixed: requires human verification (market_df 列補完・logic 変更)

### CR-05: coverage ログの %.2%% フォーマット文字列が Python で解釈不可 (ValueError)

**Files modified:** `scripts/run_backtest.py`
**Commit:** `1fc0c71`
**Applied fix:** 正しいフォーマット指定子 `%.2f%%` に修正 (% リテラルは %%・
小数2桁は %.2f・値は *100 で渡す)。実データパスの pipeline 停止を解消。

### CR-06: HARAI merge と label merge の suffix 重複で race_key 参照が曖昧になる silent 障害経路

**Files modified:** `scripts/run_backtest.py`
**Commit:** `f87b617` (CR-03 と同一コミット)
**Applied fix:** label merge の `suffixes=("", "_label")` を
`suffixes=("_left", "_label")` に変更し・左側無修飾を許さない。label 系列は常に
`_label` 付きを正として元列名に正規化。将来 pred_df に label 列が混入 (debug join 等)
した際の silent leak 経路を構造的に防止。

### CR-07: _filter_label_by_period の between が Timestamp 型と文字列型混在で境界日を silent に欠損/重複

**Files modified:** `scripts/run_backtest.py`
**Commit:** `54c3451` (WR-05 と同一コミット)
**Applied fix:** `pd.to_datetime` で race_date / start / end の型を正規化。
WR-05 の silent fallback (空結果時に未 filter の全体 label_df を返す) を廃止し
`ValueError` で fail-loud 化。CLAUDE.md が禁止する silent leak 経路を閉塞。

### CR-08: orchestrator._apply_category_map の in-place mutation が _assert_deterministic の 2 回呼出で破壊的

**Files modified:** `src/model/orchestrator.py`
**Commit:** `eb495ae` (WR-07 と同一コミット)
**Applied fix:** `_apply_category_map` の冒頭 (category_map is None チェック後) で
`feature_df = feature_df.copy()` し・呼出元 frame を保護。`_assert_deterministic` の
2 回呼出で bit-identical が崩れる SC#4 / §19.1 構造的ブロック違反を解消。
no-op (category_map=None) のみ copy しない (A5 互換・呼出側で copy 済み前提)。

## Fixed Issues (Warning)

### WR-01: etl_pool.connection() の手動コンテキスト管理が例外安全でない

**Files modified:** `scripts/run_backtest.py`
**Commit:** `b7723fa`
**Applied fix:** `with etl_pool.connection() as conn, conn.cursor() as cur:` の標準パターンに
統一。主モデル / BL-3 両パス。旧実装の `etl_pool.connection()` 2回呼出で別 connection に
なり commit/rollback が伝播しない問題を解消。

### WR-02: _assert_jodds_coverage_horse_level の no_bet_reasons set にコード上現れない sentinel 値が含まれる

**Files modified:** `scripts/run_backtest.py`
**Commit:** `944429b`
**Applied fix:** `no_bet_reasons` set から実装に存在しない `'special_value'` /
`'fukusyoflag_not_normal_sale'` を削除し `{'no_bet', 'no_bet_empty'}` に一致させる。

### WR-03: metrics.compute_backtest_metrics の非選択行 refund_flag / refund_amount が未ゼロ化

**Files modified:** `scripts/run_backtest.py`
**Commit:** `16519be`
**Applied fix:** `_zero_out_non_selected_accounting` の zero_cols に
`refund_amount` / `payout_amount` を追加し・bool 系 `refund_flag` は別途 False 化。

### WR-04: _carve_calib_from_train_tail の calib_months=6 固定で短い train 窓の BT で train が空になる silent リスク

**Files modified:** `scripts/run_backtest.py`
**Commit:** `a5584cf`
**Applied fix:** `calib_months >= train_duration_months` の早期 `ValueError` を追加。
現状 BT-1..5 (train 3年以上) は全て通過することをスタンドアロン検証で確認済み。

### WR-05: _filter_label_by_period が空結果の場合に未 filter の label_df を返す (silent フォールバック)

**Files modified:** `scripts/run_backtest.py`
**Commit:** `54c3451` (CR-07 と同一コミット)
**Applied fix:** CR-07 で fail-loud 化済み。

### WR-06: refund_accounting.determine_stake_payout の特払処理が payfukusyopay1 を無条件参照

**Files modified:** `src/ev/refund_accounting.py`
**Commit:** `3582964`
**Applied fix:** 特払時でも `_lookup_payfukusyo_pay` で選択馬と一致する slot があるか
確認し・あれば通常中り扱い (安全側フォールバック) にする。一致 slot が無い場合のみ
特払として `payfukusyopay1` を計上。`test_refund_tokubarai_harai_fixture` (全 slot '00')
は回帰せず全件 pass。
**Status:** fixed: requires human verification (JRA 特払公式ルールの最終確認推奨)

### WR-07: orchestrator._apply_category_map が feature_df を copy せず in-place で _code 列を上書き

**Files modified:** `src/model/orchestrator.py`
**Commit:** `eb495ae` (CR-08 と同一コミット)
**Applied fix:** CR-08 で copy 追加済み。

### WR-08: select_odds_snapshot の datakubun filter が '1' 文字列比較のみで NaN を考慮しない

**Files modified:** `src/ev/odds_snapshot.py`
**Commit:** `285b8f3`
**Applied fix:** `dk.notna() & (dk.astype(str).str.strip() == "1")` で NaN を
明示的に除外してから比較。将来のスキーマ変更 (int/varchar 混在) でも破綻しないよう
`.str.strip()` で正規化。

### WR-09: metrics.compute_backtest_metrics の hit_count が返還/中止行を含む集計になり得る

**Files modified:** `src/ev/metrics.py`
**Commit:** `5a63d64`
**Applied fix:** module / function 両 docstring に hit_count / hit_rate の定義と
「返還馬分母除外効果」を明記。report の hit_rate を見る利用者が誤認しないよう明確化。

### WR-11: select_odds_snapshot の assert が python -O で削除される (HIGH #3 違反)

**Files modified:** `src/ev/odds_snapshot.py`
**Commit:** `f4c5162`
**Applied fix:** `assert len(result_df) == n_expected` を `raise RuntimeError` に変更。
CLAUDE.md / HIGH #3 / `group_split.py` 規約 (リーク防止 guard は assert でなく
raise・`python -O` で削除されない) に準拠。

## Skipped Issues (Warning)

### WR-10: ev_rank._rank が行単位 df.apply で大規模予測でパフォーマンス低下

**File:** `src/ev/ev_rank.py:112`
**Reason:** REVIEW 自身が「性能は v1 scope 外・現状は機能的正確性優先で許容」
「将来 np.select でベクトル化」と明記。機能的影響がなく・明確な改善の確信が持てない
段階での vectorize は scope 外と判断。Phase 6 キャリブ指標再設計で大規模 backtest を
回す際に別途対応 (user memory: `calib-metric-phase6-rework-inputs`)。
**Original issue:** `compute_ev_and_rank` の rank 判定のみ `apply(axis=1)` で・
数十万行で顕著な性能低下の潜在リスク。

### WR-12: _attach_accounting が df.apply(determine_stake_payout, axis=1) で行単位処理

**File:** `scripts/run_backtest.py:472-496`, `scripts/run_backtest.py:729-731`
**Reason:** WR-10 と同一理由。REVIEW 自身が「性能は v1 scope 外・現状は機能的正確性優先
で許容」「将来ベクトル化」と明記。会計計算の vectorize は JRA 払戻ルールの複雑さ
(slot 照合・返還系分岐) から慎重な設計が必要で・確信を持てる明確な改善を特定できない
段階での実装は scope 外と判断。
**Original issue:** 大規模 backtest (数万行 × 25候補) で顕著な性能低下の潜在リスク。

---

_Fixed: 2026-06-21_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
