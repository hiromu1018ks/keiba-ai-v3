---
phase: 07-presentation
reviewed: 2026-06-24T00:00:00Z
depth: deep
files_reviewed: 19
files_reviewed_list:
  - .streamlit/config.toml
  - scripts/run_export_backtest_csv.py
  - scripts/run_export_predictions_csv.py
  - src/ui/__init__.py
  - src/ui/app.py
  - src/ui/backtest_tab.py
  - src/ui/calibration_tab.py
  - src/ui/csv_columns.py
  - src/ui/jyocd_map.py
  - src/ui/loaders.py
  - src/ui/prediction_tab.py
  - tests/ui/__init__.py
  - tests/ui/test_csv_columns.py
  - tests/ui/test_csv_export.py
  - tests/ui/test_loaders_readonly.py
  - tests/ui/test_readonly_guarantee.py
  - tests/ui/test_segment_schema.py
  - tests/ui/test_streamlit_api_usage.py
  - tests/ui/test_ui_render_contract.py
findings:
  critical: 3
  warning: 9
  info: 6
  total: 18
status: issues_found
---

# Phase 7: Code Review Report（deep depth）

**Reviewed:** 2026-06-24
**Depth:** deep
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Phase 7（Presentation: Streamlit ローカル read-only UI・OUT-01/OUT-02 CSV 出力 CLI・列定数 DRY 共有）の
19 ファイルを **deep depth** でレビューした。per-file 分析に加え・cross-file の import graph / call chain
（`app.py` → `prediction_tab/backtest_tab/calibration_tab` → `loaders.py` → `src/db/connection.py` → PostgreSQL
／ `load_predictions` → `fetch_jodds` + `select_odds_snapshot` → `compute_ev_and_rank` → `normalize_prediction_export_columns`
の経路）を追跡し・前回 standard review の Warning 9 + Info 6 を deep 観点で再評価した。

**read-only セキュリティ境界（D-03・ASVS V8・Phase 8 TEST-01 前提）は cross-file で成立:**

- `make_pool(role="readonly")` のみ使用・`write_cursor` / `role="etl"` 経路は UI/CLI いずれにも不存在
  （AST 検証 `test_loaders_uses_only_readonly_pool` / `test_ui_uses_only_readonly_pool`）。
- `cur.execute(SQL, params)` の parameterized query を全 SQL で遵守（`%s` placeholder・AST `BinOp`/`JoinedStr`
  SQL 構築禁止検証）。`_select_predictions` の動的 WHERE 結合も `where_clauses` にリテラル SQL 断片を
  append し params を別渡しで安全。
- `settings.dsn_masked` のみ logger 出力・生 DSN は `SecretStr` で logger 引数に渡らない（cross-file 確認）。
- `unsafe_allow_html=True` / §16.1 除外項目（ワイド/荒れ指数/コメント生成）は src/ui/ 全ファイルで不存在。

**前回 CR-01（backtest_tab recovery_rate の effective_stake 分母統一）は cross-file で修正妥当性を確認:**

`run_backtest.py:523-547::_zero_out_non_selected_accounting` が selected_flag=False 行の
`stake/effective_stake/payout/refund/profit/refund_amount/payout_amount` を全て 0 化してから
永続化するため・UI の `_build_backtest_summary` が selected_flag フィルタなしで groupby しても
effective_stake 分母は selected 行のみに押し出され・`compute_backtest_metrics`（`metrics.py`・selected 行前提）
と同口径になる。CR-01 修正は OUT-02 CSV（列そのものを出力）とも整合。

その一方で・deep 分析で **3 件の Critical** を新規検出した。最も重大なのは (1) `_build_backtest_summary` の
代表値選出（`summary.iloc[0]`）が race_date/backtest_id いずれの sort もなく複数 backtest 存在時に
「最新」label と実態が乖離する user-observable な正確性バグ（前回 WR-03 から CR 昇格）・
(2) `load_jyocd_map` / `load_segment_json` の cwd 相対パス依存が `scripts/run_export_predictions_csv.py` 経由で
CLI を別 cwd から実行すると `FileNotFoundError` で OUT-01 出力が落ちる（前回 WR-06 から cross-file 影響拡大で CR 昇格）・
(3) `_select_uma_race_meta` の merge で pred_df 側 `kettonum` が `Int64` 正規化されず n_uma_race 側（int/Int64）と
silent に空振りして bamei/wakuban が NaN になる経路が残る（前回 WR-04 から実データ経路確認で CR 昇格）。

Cross-file で新規に確認された堅牢性ギャップとして・`_select_race_times`（Step 2・select_odds_snapshot 用）と
`_select_race_times_for_merged`（Step 5・最終 DataFrame 用）が同一 `n_race` 行集合を2回 PostgreSQL から
読込む DRY 違反（前回 WR-02 を deep で再確認）や・`prediction_tab.py` の行選択 index が `st.dataframe` の
column sort 後に表示順と内部 DataFrame 行位置のズレを生じうる点（前回 WR-07）は deep でも未修正。

## Critical Issues

### CR-01: `_build_backtest_summary` の代表値（`summary.iloc[0]`）が race_date/backtest_id いずれの sort もなく「最新」表示が不確定

**File:** `src/ui/backtest_tab.py:48-70, 99`
**Issue:** 前回 standard review WR-03 を deep 分析で再評価し Critical に昇格。

`load_backtests_cached(pool)` は backtest_id フィルタなしで全件取得し・`_build_backtest_summary` は
`groupby("backtest_id")` で1行/bt_id の summary を構築する。pandas の `groupby` は（`sort=True` 既定で）
group ラベル（backtest_id 文字列）の辞書順で行を返すが・これは「最新の backtest」ではない。
その後 `backtest_tab.py:99` で `latest = summary.iloc[0]` で「最新」と称して最初の1行を
`st.metric("recovery_rate（暫定）")` / `st.metric("selected_count")` に表示する。

`backtest_id` は複合キー `{bt_name}-{policy}-{model_type}`（例: `BT-1-30min_before-lightgbm`）で・
辞書順と時系列作成順は一致しない（`BT-10-...` が `BT-2-...` より辞書順で前に来る等）。
また `race_date` 列（summary には含まれないが bt_df には存在）でのソートも不在。
結果として・ユーザに「最新 backtest の回収率（暫定）」として提示される数値が・実際には
辞書順最初の backtest（作成順・時系列順といずれも無関係）の値になる。
honest 注記（`st.warning`）で「暫定」修飾はあるものの・**どの backtest の数値かがユーザに不明**な状態は
正確性バグであり・OUT-02 CSV（全 backtest_id の生データ）と UI metric の対応関係が取れない。

`_build_backtest_summary` は bt_df から `first = group.iloc[0]` で `backtest_strategy_version`/
`train_period`/`odds_snapshot_policy` を拾うが・これらも race_date 昇順で groupby 内の先頭行を
拾う保証はない（bt_df が race_date 順で SELECT されている前提が `_select_backtests` の SQL に
`ORDER BY` なしで成立しない）。

**Fix:** summary 構築前に明示ソートする。`race_date` が bt_df に存在する（`_select_backtests` が SELECT 済）ため・
groupby の `first` が意味を持つよう race_date DESC で整列する:

```python
def _build_backtest_summary(bt_df: pd.DataFrame) -> pd.DataFrame:
    if len(bt_df) == 0:
        return pd.DataFrame(columns=[...])
    # race_date DESC で事前整列（groupby .iloc[0] が最新 race_date 行になるよう保証）
    if "race_date" in bt_df.columns:
        bt_df = bt_df.sort_values("race_date", ascending=False, kind="mergesort").reset_index(drop=True)
    rows = []
    for bt_id, group in bt_df.groupby("backtest_id", dropna=False, sort=False):
        first = group.iloc[0]  # race_date DESC 整列済なので最新レース行
        ...
    summary = pd.DataFrame(rows)
    # 表示順も race_date 最大の backtest が先頭になるよう整列（最新の暫定値を st.metric に提示）
    if "latest_race_date" in summary.columns:
        summary = summary.sort_values("latest_race_date", ascending=False).reset_index(drop=True)
    return summary
```

（`latest_race_date` 列を summary に `group["race_date"].max()` で追加するか・
`backtest_id` の作成順を示す metadata 列で sort する方針でも可。最低限 docstring で
「`.iloc[0]` は race_date DESC 整列後の最新 backtest を示す」ことを明記。）

### CR-02: `load_jyocd_map` / `load_segment_json` が cwd 相対パス依存で・CLI を別 cwd から実行すると `FileNotFoundError`

**File:** `src/ui/jyocd_map.py:18, 36` / `src/ui/loaders.py:637`
**Issue:** 前回 standard review WR-06 を cross-file で影響拡大評価し Critical に昇格。

`jyocd_map.py:18`:
```python
_CODE_TABLES_PATH = Path("src/config/code_tables.yaml")
```
`loaders.py:637`:
```python
path = Path("reports/06-segments") / f"{axis}.json"
```

両者とも cwd 相対パス。`app.py:37-39` は `_REPO_ROOT = Path(__file__).resolve().parents[2]` で
絶対パス化して `sys.path.insert` するパターンを採用し・`scripts/run_export_*.py:39-41` も
`_REPO_ROOT = Path(__file__).resolve().parent.parent` で sys.path を解決しているが・
本2 helper は cwd 暗黙依存のまま。

cross-file で影響を追うと・`scripts/run_export_predictions_csv.py:125` が `load_predictions(pool, ...)` を呼び・
`loaders.py:313` の `load_predictions` は L450 で `jyocd_map = load_jyocd_map()` を呼ぶ。
よって **`uv run python scripts/run_export_predictions_csv.py` をリポジトトルート以外の cwd から実行すると
`FileNotFoundError: src/config/code_tables.yaml` で OUT-01 CSV 出力が落ちる**。
cron 実行・CI の別 worktree・`--output` で他 dir を指定した場合は必ずこの経路が発火する。

`load_segment_json` は `calibration_tab.py`（Streamlit UI）経由のみで・UI は `streamlit run src/ui/app.py`
（cwd = repo root 前提）から起動するため実害は UI 経路では出にくいが・本 helper も
`tests/ui/test_segment_schema.py` が `SEGMENTS_DIR = Path("reports/06-segments")` で同様に cwd 依存し・
pytest の実行 cwd が非 root だと `test_all_axes_present` が `pytest.fail` する経路を残す。

`app.py` 自身も `Path(__file__).resolve()` ベースで sys.path を解決しているのに・helper 側が cwd 依存なのは
不整合（07-PATTERNS.md §Imports pattern の意図に反する）。

**Fix:** `__file__` ベースの絶対パス化:

```python
# src/ui/jyocd_map.py
_CODE_TABLES_PATH = Path(__file__).resolve().parents[2] / "src" / "config" / "code_tables.yaml"
```
```python
# src/ui/loaders.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
def load_segment_json(axis: str) -> dict[str, Any]:
    path = _REPO_ROOT / "reports" / "06-segments" / f"{axis}.json"
    ...
```
（`tests/ui/test_segment_schema.py` の `SEGMENTS_DIR` も `Path(__file__).resolve().parents[2] / "reports/06-segments"`
に修正することで pytest 実行 cwd 非依存化。）

### CR-03: `_select_uma_race_meta` の merge で pred_df 側 `kettonum` が `Int64` 正規化されず bamei/wakuban が silent に NaN になる経路

**File:** `src/ui/loaders.py:365-366` vs `442-444`
**Issue:** 前回 standard review WR-04 を deep 分析（cross-file 型整合）で再評価し Critical に昇格。

`load_predictions` の L365-366:
```python
pred_df["race_key"] = make_race_key(pred_df)
pred_df["umaban"] = pd.to_numeric(pred_df["umaban"], errors="coerce").astype("Int64")
```
は `umaban` に対しては明示的に `Int64` 正規化するが・同じ RACE_KEY 7部 PK の一部である `kettonum` に対しては
同様の正規化をしていない（`pred_df["kettonum"]` は DB から `prediction.fukusho_prediction` 経由で
取得され・psycopg3 は `kettonum`（int4）を Python int に変換するが・`pred_df` 全体を `pd.DataFrame(rows)` で
構築する際に object dtype 扱いになることがある）。

その後 L425-444 の `_select_uma_race_meta` が:
```python
merged = merged.merge(
    uma_meta[["year","jyocd","kaiji","nichiji","racenum","umaban","kettonum","bamei","wakuban"]],
    on=["year","jyocd","kaiji","nichiji","racenum","umaban","kettonum"],
    how="left",
)
```
で結合する。`uma_meta` 側の `kettonum` は `normalized.n_uma_race` から SELECT され・
`backtest_load.py:135-147` の `_INT_COLS` 規約により int 扱いされる。
pandas `merge` は merge key の dtype が異なると（object vs int64 / Int64 vs int64）
silent に空振りし・`bamei`/`wakuban` が NaN になる。
CSV/UI では `horse_name`/`枠番` が空欄になる（OUT-01 の `horse_name`/`枠番` 列）。

これは「silent fallback 禁止」（§11.3・odds_missing_policy=no_bet の精神と同一）に反し・
ユーザは「馬名が取得できなかった」ことを NIL detectives なしに気づけない。
`make_race_key` が `astype(str)` で正規化するため race_key 経由の merge（Step 2・3）は影響しないが・
`_select_uma_race_meta` は race_key でなく7部 PK 直接比較のため影響を受ける。

cross-file で `prediction_load.py` / `backtest_load.py` は `_INT_COLS = {"kettonum", ...}` で
明示的に int 正規化する規約を採用しているのに・`loaders.py` は `umaban` のみ正規化し `kettonum` を
忘れている点は一貫性違反でもある。

**Fix:** `kettonum` も `Int64` 正規化してから merge:

```python
# src/ui/loaders.py:365-366 の直後に追加
pred_df["race_key"] = make_race_key(pred_df)
pred_df["umaban"] = pd.to_numeric(pred_df["umaban"], errors="coerce").astype("Int64")
pred_df["kettonum"] = pd.to_numeric(pred_df["kettonum"], errors="coerce").astype("Int64")  # 追加
```
（`_select_uma_race_meta` 側も `uma_meta["kettonum"] = pd.to_numeric(...).astype("Int64")` で
正規化すれば更に堅牢。unit test で `kettonum` が str/object の pred_df と int の uma_meta を
渡して merge 後に bamei が NaN でないことを検証すると良い。）

## Warnings

### WR-01: `app.py`「キャッシュ更新」ボタンが `@st.cache_resource` の pool を無効化せず・DSN 切替/PostgreSQL 再起動後に再接続できない

**File:** `src/ui/app.py:85-87`
**Issue:** 前回 standard review から未修正。cross-file で `get_pool()`（L52-61）が `@st.cache_resource` で
プロセス内単一 pool を保持し・sidebar の「キャッシュ更新」ボタン（L85-87）は `st.cache_data.clear()` のみを呼ぶ。
`st.cache_data.clear()` は `load_*_cached`（`@st.cache_data`）のエントリは消去するが・
`get_pool()` の `@st.cache_resource` エントリは消去しない。そのため PostgreSQL 再起動後や
`KEIBA_DB_*` 環境変数切替後にボタンを押しても古い/壊れた pool が再利用され続け・
`st.error("PostgreSQL（keiba_readonly ロール）に接続できません。")` の定型メッセージが出るだけで
「pool まで消去する必要がある」ことにユーザが気づけない（memory: phase7-ui-live-db-bugs の指摘と整合）。

**Fix:**
```python
if st.button("キャッシュ更新", help="DB から最新データを再取得します（pool 含む）"):
    st.cache_data.clear()
    st.cache_resource.clear()  # get_pool() のキャッシュも消去（DSN 切替/PG 再起動後に再接続）
```

### WR-02: `_select_race_times` と `_select_race_times_for_merged` が同一 n_race 行集合を2回 PostgreSQL から読込む（DRY 違反・二重クエリ）

**File:** `src/ui/loaders.py:372, 479-525`
**Issue:** 前回 standard review から未修正・cross-file で経路確認。

Step 2（L369-372）の `_select_race_times(cur, pred_df)`（select_odds_snapshot 用・race_start_datetime NULL 除外済）と
Step 5（L479）の `_select_race_times_for_merged(pool, pred_df)`（最終 DataFrame の race_start_datetime 列付与用・NULL 含む全件）が
ほぼ同一の `SELECT year, jyocd, kaiji, nichiji, racenum, race_start_datetime FROM normalized.n_race WHERE year = ANY(%s) AND jyocd BETWEEN '01' AND '10'`
を2回独立に発行し・両者とも `readonly_cursor(pool)` を新たに取得する。実データ（22,213行の予測対象）では
n_race 行集合は数千行に達し・2回の PostgreSQL ラウンドトリップと pandas DataFrame 構築が無視できないオーバーヘッドになる。
両者の実装が race_key 構築・pred_keys 構築・merge で一部重複し DRY 違反。

**Fix:** Step 2 で NULL 含む全件の race_times を1回だけ取得し・select_odds_snapshot 用に
`.dropna(subset=["race_start_datetime"]).reset_index(drop=True)` で copy を渡す。
これで「HIGH-2 付帯: race_times から除外された馬は race_start_datetime も NaN・CSV では空欄」の仕様も
自然に保たれる（最終 DataFrame 側は元の全件を使うため）:

```python
# Step 2: NULL 含む全件を1回だけ取得
race_times_full = _select_race_times_for_merged(pool, pred_df)
# select_odds_snapshot 用は dropna copy を渡す
race_times_for_snapshot = (
    race_times_full.dropna(subset=["race_start_datetime"]).reset_index(drop=True)
    if len(race_times_full) > 0
    else race_times_full
)
snapshot_df = select_odds_snapshot(jodds_df, race_times_for_snapshot, policy=odds_snapshot_policy)
# Step 5 では race_times_full を再利用（再クエリしない）
```

### WR-04: `normalize_date_range` の `pd.Timestamp(raw).date()` が NaT 入力で `AttributeError`（未捕捉）

**File:** `src/ui/loaders.py:159, 162-163, 169-171`
**Issue:** 前回 standard review から未修正。

`st.date_input` の戻り値 `raw` は通常 `datetime.date` の list だが・`pd.Timestamp(date)` の変換が
`NaT` を返した場合（`date` が NaT・parser が解釈不能）でも例外を raise せず
`.date()` が `pd.libs.tslibs.nattype.NaTType` に対して `AttributeError` を出す。
L171 の `except (TypeError, ValueError)` は `AttributeError` を捕捉せず・UI が 500 系例外で落ちる経路が残る。

**Fix:**
```python
except (TypeError, ValueError, AttributeError):
    return (None, None)
```

### WR-05: `prediction_tab.py` の行選択 index が `race_list_df.iloc[selected_idx]` で・column sort 後に表示順と内部行位置がズレる

**File:** `src/ui/prediction_tab.py:153-167`
**Issue:** 前回 standard review WR-07 から継続。cross-file で Streamlit 1.58 の `st.dataframe(..., on_select="rerun")` の
`event.selection["rows"]` が「表示上の行 index」を返す挙動を確認。

`race_list_df = _build_race_list_df(pred_df)` は `race_date DESC` で整列済だが・`st.dataframe` は
列ヘッダクリックでユーザが column sort を行える（Streamlit 既定）。sort 後の `event.selection["rows"]` は
表示順の行 index を返すが・`race_list_df.iloc[selected_idx]`（L167）は内部 DataFrame の行位置を参照するため・
sort 後は選択したレースと異なる race_id が選ばれる経路が残る。
memory: phase7-ui-live-db-bugs の「unit test の `KEIBA_SKIP_DB_TESTS` では検出不可」に該当し・
実データでのみ発覚するリスク。

**Fix:** `event.selection` から取得できる row index を DataFrame の `iloc` に使わず・
`race_list_df` に reset_index で明示行番号列を持たせ・selection の row をその列で逆引きする設計にする。
最低限ドキュメントで「列 sort 後の選択ズレ」注意書きを入れる:

```python
# 案: row index でなく race_id で直接特定できるよう・selection から取れた index で
# race_list_df を iloc する前に表示順と一致させるため column sort を無効化するか
# race_list_df 自体を表示専用 copy にして .iloc が表示行と一致するよう lock する。
# Streamlit 1.58 では st.dataframe の column sort 無効化フラグがないため・
# 選択後に race_list_df.iloc[selected_idx]["race_id"] で逆引きし・
# pred_df 側で race_id が一意（race_list_df groupby で一意保証）である前提を docstring 明記。
```

### WR-06: `calibration_tab.py` の `scalar_rows` が segment JSON の余剰キーを未検証で `pd.DataFrame` に渡す（表示崩れ/例外リスク）

**File:** `src/ui/calibration_tab.py:110-117`
**Issue:** 前回 standard review WR-08 から継続・cross-file で JSON 入力スキーマ検証の弱さを再確認。

`scalar_rows` は `seg.get("scalar", {})` をそのまま `dict.update` で展開するため・
JSON に想定外のキー（例: float・list・nested dict）が含まれていても `pd.DataFrame(scalar_rows)` が呼ばれる。
`pd.DataFrame(rows)` は異種スキーマの row があると列が object dtype になり・表示崩れや
`ValueError: mixing dicts with non-Series` 等の例外が起きうる。
`test_segment_schema.py` は `REQUIRED_SCALAR_KEYS <= set(...)` の部分集合検証のみで・
余剰キーや型不整合は検出しない（`float` vs `str` の `max_dev_guarded` 等も pass する）。

**Fix:** 表示前に明示的に5キーのみ抽出（WR-08 修正案を再掲）:
```python
SCALAR_DISPLAY_KEYS = ("ece_quantile", "ece_uniform", "max_dev_guarded", "mce_guarded", "n_samples")
for seg in seg_data.get("segments", []):
    sc = seg.get("scalar", {})
    row = {"segment_value": seg.get("segment_value", "")}
    for k in SCALAR_DISPLAY_KEYS:
        row[k] = sc.get(k)
    scalar_rows.append(row)
```

### WR-07: `run_export_*.py` の `main()` が `PsycopgError` 以外の例外を握り潰し・一意の exit code を返さない

**File:** `scripts/run_export_backtest_csv.py:88-103`, `scripts/run_export_predictions_csv.py:122-144`
**Issue:** 前回 standard review WR-09 から継続。

両 CLI の `main()` は `try/except PsycopgError` のみで catch し・成功時 `return 0`・DB エラー時 `return 3`。
しかし `load_predictions`/`build_*_csv_bytes` が `ValueError`（必須列欠落）や `FileNotFoundError`
（CR-02 の cwd 依存経路）・`pd.errors.ParserError` 等を raise した場合・except 節を素通りして
`main()` の外に飛び・`sys.exit(main())` で traceback 表示 → exit 1 になる。
CI で exit code を区別する場合に不都合（DB エラーとそれ以外が区別できない）。

**Fix:** `except Exception as exc:` を追加して logger.error + 一意の exit code を返す:
```python
except PsycopgError as exc:
    logger.error("DB エラーで OUT-02 出力失敗: %s", exc)
    return 3
except Exception as exc:
    logger.error("OUT-02 出力失敗（DB 以外のエラー）: %s", exc, exc_info=True)
    return 2
```

### WR-08: `_build_backtest_summary` の `group.get("effective_stake", pd.Series([0]))` fallback が列不在時に silent に空集計を黙認

**File:** `src/ui/backtest_tab.py:52-59`
**Issue:** 前回 standard review IN-03 を deep 観点で再評価し Warning に昇格。

`group.get("effective_stake", pd.Series([0]))` は列が存在しない場合に `pd.Series([0])` を返す。
これは「effective_stake 列が欠損」という異常状態を silent に握り潰し・`total_effective_stake = 0` で
`recovery = float("nan")` になり・UI には「N/A」と表示される。
loaders 契約上 `load_backtests` は `_select_backtests` で `BACKTEST_COLUMNS` 全列を SELECT するため実害はないが・
将来 `BACKTEST_COLUMNS` から `effective_stake` が外れた場合に silent に回収率が N/A になる経路を残す。
defensive code としては fail-loud の方が望ましい（`compute_backtest_metrics` は `df["effective_stake"].sum()` で
列不在時は `KeyError` で落ちる設計）。

**Fix:**
```python
REQUIRED_COLS = ("effective_stake", "payout_amount", "selected_flag")
missing = [c for c in REQUIRED_COLS if c not in group.columns]
if missing:
    raise ValueError(f"backtest DataFrame に必須列がない: {missing} (loaders 契約違反)")
```

### WR-09: `test_streamlit_api_usage.py::_RACE_LIST_VAR_CANDIDATES` が変数名ハードコードで・リファクタでテストが迂回される

**File:** `tests/ui/test_streamlit_api_usage.py:31, 88-90`
**Issue:** 前回 standard review IN-04 を deep 観点で再評価し Warning に昇格。

`_RACE_LIST_VAR_CANDIDATES = {"race_list_df", "race_df", "master_df"}` は変数名で race-list master dataframe を識別する。
`prediction_tab.py` が変数名を `races` 等にリファクタした場合・`test_dataframe_uses_selection_mode` は
`pytest.skip("race-list master dataframe の st.dataframe 呼出が見つかりません...")` してしまい・
実質検査しなくなる（silent test bypass）。これは RESEARCH Pitfall 1（selection_mode 正引数）の
回帰検出網を抜ける経路を残す。

**Fix:** 変数名でなく・`selection_mode` を持つ `st.dataframe` が少なくとも1つ存在すること・
または `_build_race_list_df` を呼出す関数内の `st.dataframe` を AST で特定する方式に変更:
```python
# race-list 構築関数 (_build_race_list_df) の戻りを capture する変数に依存しないよう・
# module 内に selection_mode='single-row' を持つ st.dataframe が1つ以上存在することを検証。
def test_dataframe_uses_selection_mode():
    calls = _collect_dataframe_calls()
    if not calls:
        pytest.skip("src/ui/ に st.dataframe 呼出がない")
    has_any_selection_mode = any(
        any(kw.arg == "selection_mode" for kw in call.keywords) for _, call in calls
    )
    assert has_any_selection_mode, "src/ui/ に selection_mode を持つ st.dataframe が存在しない"
```

## Info

### IN-01: `build_*_csv_bytes` の `to_csv(encoding="utf-8-sig")` が str 戻りに対し実質 no-op（冗長引数）

**File:** `src/ui/loaders.py:724, 744`
**Issue:** 前回 standard review から継続（cross-file で影響なし・可読性）。

`df.to_csv(index=False, encoding="utf-8-sig", lineterminator="\r\n")` は `str` を返すが・
pandas の `to_csv` は `encoding="utf-8-sig"` をファイル出力時のみ適用し・str 戻りには BOM を付与しない。
その後 `.encode("utf-8-sig")` が単一の BOM を付与する。結果として単一 BOM で正しいが・
`encoding="utf-8-sig"` 引数は無意味で可読性を下げる。

**Fix:** `to_csv(index=False, lineterminator="\r\n")`（encoding 省略）→ `.encode("utf-8-sig")`。

### IN-02: `csv_columns.py` の `TYPE_CHECKING` 下 import `pd` が `from __future__ import annotations` のもとで厳密には不要

**File:** `src/ui/csv_columns.py:42-45, 121`
**Issue:** 前回 standard review から継続。

`if TYPE_CHECKING: import pandas as pd` は `normalize_prediction_export_columns(df: pd.DataFrame)` の
型ヒント解決用。`from __future__ import annotations` があるため・型ヒントは全て文字列扱いで・
`TYPE_CHECKING` ブロックは厳密には不要（実行時未参照）。mypy/pyright 用の doc 的意味合いのみ。

**Fix:** 特に修正不要だが・`TYPE_CHECKING` ブロック削除でも可。

### IN-03: `test_ui_render_contract.py::test_no_unsafe_allow_html` が単純文字列検索（コメント/docstring で false positive）

**File:** `tests/ui/test_ui_render_contract.py:352-359`
**Issue:** 前回 standard review IN-05 から継続。

`"unsafe_allow_html=True" in source` は AST でなく文字列包含検索のため・docstring やコメントで
「`unsafe_allow_html=True` を使ってはならない」という説明文があるだけで false positive になる。
現状 src/ui/ には該当説明文はないが・将来 docstring 追加で壊れる。

**Fix:** AST で `ast.Call.keywords` の `kw.arg == "unsafe_allow_html"` を検索する方式に変更。

### IN-04: `test_segment_schema.py` の必須キー検証が「部分集合」で・余剰/型不整合（float vs str）を検出しない

**File:** `tests/ui/test_segment_schema.py:63-68`
**Issue:** 前回 standard review IN-06 から継続。WR-06 と合わせて上流要因。

`REQUIRED_CURVE_KEYS <= set(seg["curve"])` は部分集合検証のため・curve に余剰キーや
`mean_pred` が list でなく dict であっても pass する。これが WR-06 で指摘した表示崩れの上流要因。

**Fix:** WR-06 と併せて・テスト側で「curve/scalar の各キーが list/float/int であること」を型検証。

### IN-05: `jyocd_map.py::load_jyocd_map` が `dict(data["jyocd"])` で YAML トップレベルキー不在時に `KeyError`（fail-loud だがメッセージ不親切）

**File:** `src/ui/jyocd_map.py:36-37`
**Issue:** deep で新規検出（軽微）。

`yaml.safe_load(...)` の戻りが `{"jyocd": {...}}` でない場合（YAML 構造変更・空ファイル）に
`data["jyocd"]` で `KeyError` になる。fail-loud ではあるが・`KeyError: 'jyocd'` では
原因（code_tables.yaml の構造）が利用者に伝わりにくい。CR-02 の絶対パス化修正と併せるなら
親切なエラーメッセージ化も推奨。

**Fix:**
```python
data = yaml.safe_load(_CODE_TABLES_PATH.read_text(encoding="utf-8"))
if not isinstance(data, dict) or "jyocd" not in data:
    raise ValueError(f"{_CODE_TABLES_PATH} に 'jyocd' セクションがない（構造変更の可能性）")
return dict(data["jyocd"])
```

### IN-06: `prediction_tab.py::_build_race_list_df` の groupby キーに日本語列名（`競馬場`/`レース番号`）を含めると列名依存が暗黙

**File:** `src/ui/prediction_tab.py:70-77`
**Issue:** deep で新規検出（軽微・設計一貫性）。

`groupby(["race_id", "race_date", "競馬場", "レース番号"], dropna=False)` は派生列（日本語名）を
groupby キーにする。`load_predictions` がこれらの列名（`競馬場`/`レース番号`/`馬番`）を
ハードコードで付与する（`loaders.py:451, 464, 468`）ため・両モジュール間に暗黙の列名契約ができる。
列名変更すると groupby が `KeyError` になるが・この契約が docstring に明記されていない。

**Fix:** `PREDICTION_CSV_COLUMNS` の日本語列名を定数化（例: `COLUMN_RACECOURSE = "競馬場"`）して
loaders と prediction_tab で共有し・契約を明示する。または docstring で
「`_build_race_list_df` は `競馬場`/`レース番号`/`馬番` 列の存在を前提とする」ことを明記。

---

_Reviewed: 2026-06-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
