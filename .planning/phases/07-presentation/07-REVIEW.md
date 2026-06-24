---
phase: 07-presentation
reviewed: 2026-06-24T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - src/ui/app.py
  - src/ui/backtest_tab.py
  - src/ui/calibration_tab.py
  - src/ui/csv_columns.py
  - src/ui/jyocd_map.py
  - src/ui/loaders.py
  - src/ui/prediction_tab.py
  - scripts/run_export_backtest_csv.py
  - scripts/run_export_predictions_csv.py
  - tests/ui/test_csv_columns.py
  - tests/ui/test_csv_export.py
  - tests/ui/test_loaders_readonly.py
  - tests/ui/test_readonly_guarantee.py
  - tests/ui/test_segment_schema.py
  - tests/ui/test_streamlit_api_usage.py
  - tests/ui/test_ui_render_contract.py
findings:
  critical: 1
  warning: 9
  info: 6
  total: 16
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-24
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Phase 7（Presentation・読込専用 Streamlit UI／CSV 出力 CLI／列定数 DRY 共有）の16ファイルを
standard depth でレビューした。read-only 保証（D-03・`make_pool(role="readonly")` のみ・
書込み/DDL SQL リテラル不存在・AST 検証）、ASVS V8 DSN 非開示（`dsn_masked` のみ logger 出力）、
§16.1 除外（ワイド/荒れ指数/コメント生成）の不存在、PostgreSQL 引用符付き識別子（`"EV_lower"`/
`"EV_upper"`）の正使用（commit ef83b1e 修正状態）、パラメタ化クエリ（`%s` placeholder）の遵守は
概ね成立している。主要な堅牢性ギャップと軽微な品質問題を16件検出した。最も重大な CR-01 は
`backtest_tab.py::_build_backtest_summary` の `recovery_rate` 計算が `BACKTEST_CSV_COLUMNS`
が公開する `stake` 列の口径と一致しない可能性（`effective_stake` vs `stake`・§11.6 払戻規則）。
また `app.py` の「キャッシュ更新」ボタンが `@st.cache_resource` で保持される pool を無効化
しないため、UI 実行時に DSN 切替/PostgreSQL 再起動後の再接続経路が欠如している点も指摘した。

## Critical Issues

### CR-01: `_build_backtest_summary` の `recovery_rate` 計算が `effective_stake` を無視（§11.6 回収率口径）

**File:** `src/ui/backtest_tab.py:46-48`
**Issue:** backtest サマリの回収率 `recovery_rate = total_payout / total_stake` は `stake` 列を
分母に使用しているが・プロジェクトの会計規則（§11.6・CLAUDE.md `src/ev/purchase_simulator`）では
返金・競走中止・`refund_flag=True` 行を含む会計には `effective_stake` を使用することが明示されている
（`BACKTEST_COLUMNS` に `effective_stake` が独立列として存在・`schema.py:172`）。

`loaders.py::_select_backtests` は両方の列を SELECT しているため・UI summary 側で `effective_stake`
を採用することは技術的に可能だが・現状は `group.get("stake", ...)` のみを使い・返金行の stake を
含んだまま回収率を算出している。結果として返金行（refund_flag=True・`payout_amount=0`・`stake=0` の
ことが多いが・「返金行の stake」の扱いは purchase_simulator の定義次第）の取り扱いが曖昧で・
表示される「暫定」回収率が OUT-02 CSV (`BACKTEST_CSV_COLUMNS`) が公開する `stake`/`profit`/
`payout_amount` と乖離する可能性がある。§19.1 再現性の観点でも・UI とレポートで回収率口径が
複数存在することは望ましくない。

加えて・`_build_backtest_summary` は `selected_flag=False` の除外候補行（MEDIUM-04・no_bet/
special_value/no_sale/scratch_cancel の監査用永続化行・`src/db/backtest_load.py` docstring 参照）
も含めて groupby で集計しており・`stake` が 0 でない除外候補行が混入すると回収率が不当に低下する。
CSV 側は列そのものを出力するため口径問題は無いが・UI summary の `st.metric("recovery_rate（暫定）")`
は単一の分母子を仮定しており・ユーザ解釈の当事者能力に依存する。

**Fix:**
```python
# selected_flag=True の行のみで会計列を集計し・effective_stake を分母に使用（§11.6 扇子返金/中止含む）
sel = group[group["selected_flag"].fillna(False).astype(bool)] if "selected_flag" in group.columns else group
total_stake = float(sel.get("effective_stake", sel.get("stake", pd.Series([0]))).fillna(0).sum())
total_payout = float(sel.get("payout_amount", pd.Series([0])).fillna(0).sum())
recovery = (total_payout / total_stake) if total_stake > 0 else float("nan")
```
（参照: `src/db/backtest_load.py` docstring MEDIUM-04・`BACKTEST_COLUMNS` effective_stake 列・§11.6）

## Warnings

### WR-01: `app.py` 「キャッシュ更新」ボタンが `@st.cache_resource` の pool を無効化せず・再起動/DSN 切替後に再接続できない

**File:** `src/ui/app.py:85-87`
**Issue:** sidebar の「キャッシュ更新」ボタンは `st.cache_data.clear()` のみを呼ぶ。これは
`load_*_cached` の `@st.cache_data` エントリは消去するが・`get_pool()` の `@st.cache_resource`
エントリは消去しない。そのため・PostgreSQL が再起動した後・または `KEIBA_DB_*` 環境変数を
切替えた後にボタンを押しても既存の（古い/壊れた）pool オブジェクトが再利用され続ける。pool が
クローズされている場合でもエラーメッセージは同じ `st.error` 定型文に出るだけで・ユーザは
「キャッシュ更新」が効かない原因（pool まで消去する必要がある）に気づけない。

**Fix:**
```python
if st.button("キャッシュ更新", help="DB から最新データを再取得します（pool 含む）"):
    st.cache_data.clear()
    st.cache_resource.clear()  # get_pool() のキャッシュも消去（DSN 切替/PG 再起動後に再接続）
```

### WR-02: `load_predictions` の race_start_datetime 取得で同一 SQL が2回実行される（`_select_race_times` + `_select_race_times_for_merged`）

**File:** `src/ui/loaders.py:372, 479-525`
**Issue:** Step 2 の `_select_race_times(cur, pred_df)`（select_odds_snapshot 用・race_start_datetime
NULL 除外済）と Step 5 の `_select_race_times_for_merged(pool, pred_df)`（最終 DataFrame の
race_start_datetime 列付与用・NULL 含む全件）は・ほぼ同一の `SELECT ... FROM normalized.n_race
WHERE year = ANY(%s) AND jyocd BETWEEN '01' AND '10'` を2回独立に発行する。両者とも
`readonly_cursor(pool)` を新たに取得し直す。結果として・同じ n_race 行集合を2回 PostgreSQL から
読み込むことになり・予測対象が大きい場合に無視できないオーバーヘッドになる。また両者の実装が
一部重複（race_key 構築・pred_keys 構築・merge）しており・DRY 違反。

正しい修正は Step 2 で NULL 含む全件の race_times を1回だけ取得し・select_odds_snapshot 用に
`.dropna(subset=["race_start_datetime"])` で絞った copy を渡すこと。これで「HIGH-2 付帯:
race_times から除外された馬は NaN」の仕様も自然に保たれる（最終 DataFrame 側は元の全件を使うため）。

**Fix:**
```python
# Step 2: race_times を NULL 含む全件で1回だけ取得
race_times_full = _select_race_times_for_merged(pool, pred_df)
# select_odds_snapshot 用は dropna copy を渡す（破壊的でなく copy）
race_times_for_snapshot = race_times_full.dropna(subset=["race_start_datetime"]).reset_index(drop=True)
# ... Step 3-5 で race_times_full を最終 DataFrame 付与に使う
```

### WR-03: `_build_backtest_summary` の `recovery_rate` が複数 backtest_id で混在（summary.iloc[0] の代表値が不確定）

**File:** `src/ui/backtest_tab.py:85-98`
**Issue:** `load_backtests_cached(pool)` は backtest_id フィルタなしで全件取得し・
`_build_backtest_summary` は `groupby("backtest_id")` で1行/bt_id の summary を作る。その後
`summary.iloc[0]` で「latest」と称して最初の1行を `st.metric("recovery_rate（暫定）")` に表示するが・
pandas は `groupby` 後の行順序を（sort を指定しなければ）最初に出現した bt_id 順にするため・
これが「最新」である保証はない（race_date や backtest_id 作成順でのソート不在）。ユーザに提示される
回収率がどの backtest 由来か不明。

**Fix:** summary を代表値選出前に race_date 最大 または backtest_id 辞書順最大 で明示ソートする:
```python
if "race_date" in summary.columns:
    summary = summary.sort_values("race_date", ascending=False).reset_index(drop=True)
# または backtest_id で安定 sort
```

### WR-04: `_select_uma_race_meta` が `kettonum` を結合キーに使うが pred_df 側の `kettonum` 型が未正規化（`Int64` 変換なし）

**File:** `src/ui/loaders.py:365-366 vs 442-444`
**Issue:** `load_predictions` は `umaban` に対して `pd.to_numeric(..., errors="coerce").astype("Int64")`
を明示的に行う（L366）が・同じ PK の一部である `kettonum` に対しては同様の正規化をしていない。
その後 `_select_uma_race_meta` が `merged.merge(... on=["year","jyocd","kaiji","nichiji","racenum","umaban","kettonum"])`
で結合する際・pred_df 側の `kettonum` が str/obj のままで・n_uma_race 由来の `kettonum` が int/Int64 の場合
マージが空振り（silent に bamei/wakuban が NaN）する可能性がある。これは「silent fallback 禁止」
（§11.3）の精神と整合しない。

**Fix:** `pred_df["kettonum"]` も `pd.to_numeric(..., errors="coerce").astype("Int64")` で正規化してから merge。

### WR-05: `normalize_date_range` が `pd.Timestamp(raw[0])` で `pd.Timestamp` への暗黙依存（pyarrow/NaT チェックの副作用リスク）

**File:** `src/ui/loaders.py:159-172`
**Issue:** `st.date_input` から渡される `raw` は通常 `datetime.date` の list だが・`pd.Timestamp(date)`
の変換が `NaT` を返した場合（`date` が NaT・または parser が解釈不能）でも例外を raise せず
`.date()` が `pd.libs.tslibs.nattype.NaTType` に対して AttributeError を出す。`except (TypeError, ValueError)`
で AttributeError を捕捉しないため・UI が 500 系例外で落ちる経路が残る。

**Fix:**
```python
except (TypeError, ValueError, AttributeError):
    return (None, None)
```

### WR-06: `jyocd_map.py::load_jyocd_map` が cwd 依存の相対パスを使う（`streamlit run` 以外の import で FileNotFound）

**File:** `src/ui/jyocd_map.py:18, 36`
**Issue:** `_CODE_TABLES_PATH = Path("src/config/code_tables.yaml")` は相対パスで・cwd が
プロジェクトルートでない場合（例: pytest のルートが別ディレクトリ・CLI の `--output` で
他 dir を指定・cron 実行）に `FileNotFoundError` になる。`app.py` は `sys.path.insert` で
明示的にルートを解決しているのに対し・本 helper は cwd 暗黙依存。`load_predictions` が本 helper
を呼ぶため・CLI (`run_export_predictions_csv.py`) 経由でも同様のリスク。

**Fix:** `__file__` ベースで絶対パス化:
```python
_CODE_TABLES_PATH = Path(__file__).resolve().parents[2] / "src" / "config" / "code_tables.yaml"
```

### WR-07: `prediction_tab.py::render_prediction_tab` の行選択 index が `race_list_df` の行位置に依存（race_id 一意性の暗黙前提）

**File:** `src/ui/prediction_tab.py:166-171`
**Issue:** `selected_idx = rows[0]; selected_race = race_list_df.iloc[selected_idx]` で選択行を特定し・
その後 `selected_race_id` で `pred_df[pred_df["race_id"] == selected_race_id]` で絞る。これは Streamlit
の `selection_mode="single-row"` が `race_list_df` の表示行 index を返す前提に立つが・ユーザが
column sort（`st.dataframe` のデフォルトで列ヘッダクリック可能）した場合・`event.selection["rows"]`
は表示上の行 index を返し・`race_list_df.iloc[selected_idx]` は内部 DataFrame の行 index を参照するため・
ズレが生じうる。これは Streamlit Community の既知挙動（sorted view の row index は表示順）。

**Fix:** `event.selection` から取得できる row index を DataFrame の `iloc` に使わず・
`st.dataframe(..., on_select="rerun")` の戻りが `selection["rows"]` の他にキー列を返さない場合は・
`race_list_df` に reset_index で明示行番号列を持たせ・selection の row をその列で逆引きする設計にする。
最低限ドキュメントで「列 sort 後の選択ズレ」注意書きを入れる。

### WR-08: `calibration_tab.py` の `scalar_rows` 表で segment_value 以外の列が JSON 入力由来でスキーマ未検証

**File:** `src/ui/calibration_tab.py:110-117`
**Issue:** `scalar_rows` は `seg.get("scalar", {})` をそのまま `dict.update` で展開するため・
JSON に想定外のキー（例: float・list・nested dict）が含まれていても `st.dataframe(pd_safe(scalar_rows))`
が呼ばれる。`pd.DataFrame(rows)` は異種スキーマの row があると列が object dtype になり・表示崩れや
`ValueError: mixing dicts with non-Series` 等の例外が起きうる。`test_segment_schema.py` は
`REQUIRED_SCALAR_KEYS <= set(...)` の部分集合検証のみで・余剰キーや型不整合は検出しない。

**Fix:** 表示前に明示的に5キー（ece_quantile/ece_uniform/max_dev_guarded/mce_guarded/n_samples）のみ抽出:
```python
SCALAR_DISPLAY_KEYS = ("ece_quantile", "ece_uniform", "max_dev_guarded", "mce_guarded", "n_samples")
for seg in seg_data.get("segments", []):
    sc = seg.get("scalar", {})
    row = {"segment_value": seg.get("segment_value", "")}
    for k in SCALAR_DISPLAY_KEYS:
        row[k] = sc.get(k)
    scalar_rows.append(row)
```

### WR-09: `run_export_*.py` のメインが `PsycopgError` 以外の例外を握り潰し・exit code 1 を返さない（`main()` が None → `sys.exit(None)` → exit 0）

**File:** `scripts/run_export_backtest_csv.py:88-103`, `scripts/run_export_predictions_csv.py:122-144`
**Issue:** 両 CLI の `main()` は `try/except PsycopgError` のみで catch し・成功時 `return 0`・
DB エラー時 `return 3`。しかし `load_predictions`/`build_*_csv_bytes` が `ValueError`（必須列欠落）や
`FileNotFoundError`・`pd.errors.ParserError` 等を raise した場合・except 節を素通りして `main()` の外に
飛び・`if __name__ == "__main__": sys.exit(main())` の `main()` 呼出で例外 propagate → traceback 表示 →
exit 1。これは意図的かもしれないが・REVIEW MEDIUM-2 で明記された「fail-loud」原則と整合する一方で・
`build_prediction_csv_bytes` の `ValueError` を含む一般例外を `except Exception as exc: logger.error(...); return 2`
等で明示的に扱うべき。現状は「PsycopgError 以外は未処理」と見え・CI で exit code を区別する場合に不都合。

**Fix:** `except Exception as exc:` を追加して logger.error + 一意の exit code（例: `return 2`）を返す。

## Info

### IN-01: `loaders.py::build_*_csv_bytes` の `to_csv(encoding="utf-8-sig")` は str 戻りに対し実質 no-op（冗長引数）

**File:** `src/ui/loaders.py:724, 744`
**Issue:** `df.to_csv(index=False, encoding="utf-8-sig", lineterminator="\r\n")` は `str` を返すが・
Python の pandas `to_csv` は `encoding="utf-8-sig"` をファイル出力時のみ適用し・str 戻りには BOM を付与しない
（実測: `csv_str` の先頭は `'a,b\r\n'` で BOM なし）。その後 `.encode("utf-8-sig")` が単一の BOM を付与する。
結果として単一 BOM で正しいが・`encoding="utf-8-sig"` 引数は無意味で可読性を下げる。

**Fix:** `to_csv(index=False, lineterminator="\r\n")`（encoding 省略）→ `.encode("utf-8-sig")`。

### IN-02: `csv_columns.py` の `TYPE_CHECKING` 下 import `pd` が型検査以外で実質未使用（helper シグネチャは文字列参照）

**File:** `src/ui/csv_columns.py:42-45, 121`
**Issue:** `if TYPE_CHECKING: import pandas as pd` は `normalize_prediction_export_columns(df: pd.DataFrame)`
の型ヒント解決用。実行時には未使用だが・ruff は `TYPE_CHECKING` 下 import を許容するため問題ない。
ただし `from __future__ import annotations` があるため・型ヒントは全て文字列扱いで・`TYPE_CHECKING`
ブロックは厳密には不要（実行時未参照）。mypy/pyright 用の doc 的意味合いのみ。

**Fix:** 特に修正不要だが・`from __future__ import annotations` の下では `TYPE_CHECKING` ブロック削除でも可。

### IN-03: `backtest_tab.py::_build_backtest_summary` の `group.get("stake", pd.Series([0]))` fallback が列不在時に空集計を黙認

**File:** `src/ui/backtest_tab.py:46-50`
**Issue:** `group.get("stake", pd.Series([0]))` は列が存在しない場合に `pd.Series([0])` を返すが・
これは「stake 列が欠損」という異常状態を silent に握り潰す。loaders 契約上 `load_backtests` は
`BACKTEST_CSV_COLUMNS` 全列を返すため実害はないが・defensive code としては fail-loud の方が望ましい。

**Fix:** `if "stake" not in group.columns: raise ValueError(...)` または docstring で前提明記。

### IN-04: `test_streamlit_api_usage.py::_RACE_LIST_VAR_CANDIDATES` が変数名ハードコード（リファクタでテスト迂回）

**File:** `tests/ui/test_streamlit_api_usage.py:31, 88-90`
**Issue:** `_RACE_LIST_VAR_CANDIDATES = {"race_list_df", "race_df", "master_df"}` は変数名で
race-list master dataframe を識別する。`prediction_tab.py` が変数名を `races` 等にリファクタした場合・
`test_dataframe_uses_selection_mode` は `pytest.skip` してしまい・実質検査しなくなる（silent test bypass）。

**Fix:** 変数名でなく・`selection_mode` を持つ `st.dataframe` が少なくとも1つ存在すること・
または `_build_race_list_df` を呼出す関数内の `st.dataframe` を AST で特定する方式に変更。

### IN-05: `test_ui_render_contract.py::test_no_unsafe_allow_html` が単純文字列検索（コメント内の "unsafe_allow_html=True" 説明で false positive）

**File:** `tests/ui/test_ui_render_contract.py:355-358`
**Issue:** `"unsafe_allow_html=True" in source` は AST でなく文字列包含検索のため・docstring や
コメントで「`unsafe_allow_html=True` を使ってはならない」という説明文があるだけで false positive になる。
現状 src/ui/ には該当説明文はないが・将来 docstring 追加で壊れる。

**Fix:** AST で `ast.Call.keywords` の `kw.arg == "unsafe_allow_html"` を検索する方式に変更。

### IN-06: `test_segment_schema.py` の必須キー検証が「部分集合」で・余剰/型不整合（float vs str）を検出しない

**File:** `tests/ui/test_segment_schema.py:63-68`
**Issue:** `REQUIRED_CURVE_KEYS <= set(seg["curve"])` は部分集合検証のため・curve に余剰キーや
`mean_pred` が list でなく dict であっても pass する。これが WR-08 で指摘した表示崩れの上流要因。

**Fix:** WR-08 と併せて・テスト側で「curve/scalar の各キーが list/float/int であること」を型検証。

---

_Reviewed: 2026-06-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
