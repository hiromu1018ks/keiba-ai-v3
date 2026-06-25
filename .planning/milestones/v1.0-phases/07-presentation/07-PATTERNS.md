# Phase 7: Presentation - Pattern Map

**Mapped:** 2026-06-24
**Files analyzed:** 11 新規/修正ファイル
**Analogs found:** 11 / 11（全ファイルに既存コード analog あり）

---

## File Classification

| 新規/修正ファイル | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ui/__init__.py` | config（パッケージ化） | — | `src/db/__init__.py` / `src/ev/__init__.py` | exact（慣例） |
| `src/ui/csv_columns.py` | utility（定数・DRY 列 pin） | transform（列整列） | `src/ev/report.py::REPORT_COLUMNS`（L41-53）・`src/db/backtest_load.py::BACKTEST_COLUMNS`（L77-116）・`src/model/predict.py::PREDICTION_COLUMNS`（L63-86） | exact（同思想の tuple 定数） |
| `src/ui/loaders.py` | service（DB/JSON 読込） | request-response（SELECT）・file-I/O（JSON 読込） | `src/db/connection.py::readonly_cursor`（L66-76）+ `tests/conftest.py::pg_pool/readonly_cur`（L33-48） | role-match（readonly SELECT パターン） |
| `src/ui/jyocd_map.py` | utility（コード→名称） | file-I/O（YAML 読込） | `src/config/code_tables.yaml`（L9-21）+ 既存 YAML 読込慣例 | exact（同一ファイルが入力） |
| `src/ui/app.py` | component（Streamlit エントリ） | request-response（UI rerun） | `scripts/run_backtest.py::main/_run_pipeline`（L1011-1302・entry pattern・Settings/masked DSN/try-finally） | role-match（同プロジェクトの entry point 慣例） |
| `src/ui/prediction_tab.py` | component（UI タブ） | request-response | `scripts/run_backtest.py::_run_main_model_backtest`（L553-766・merge + metrics 構築）+ `src/ev/report.py`（L106-135 手動表生成） | role-match（データ組み立て・表示） |
| `src/ui/backtest_tab.py` | component（UI タブ） | request-response | `src/ev/report.py::generate_report`（L176-274）+ BACKTEST_COLUMNS 構造 | role-match |
| `src/ui/calibration_tab.py` | component（UI タブ・Plotly） | file-I/O（JSON）→ transform（Figure） | `reports/06-segments/year.json`（実スキーマ）+ Plotly 慣例 | partial（UI 新規・JSON スキーマは確定） |
| `scripts/run_export_predictions_csv.py` | route（CLI・argparse） | batch（CSV 出力） | `scripts/run_backtest.py`（L36-168・argparse/Settings/masked DSN/output-dir） | exact（同ディレクトリの CLI 慣例） |
| `scripts/run_export_backtest_csv.py` | route（CLI・argparse） | batch（CSV 出力） | `scripts/run_backtest.py`（同上） | exact |
| `pyproject.toml`（修正） | config | — | 既存 `pyproject.toml`（L10-26 dependencies・L32-33 wheel packages） | exact（同一ファイル編集） |
| `.streamlit/config.toml`（新規） | config | — | UI-SPEC Color Contract（Theme light・primaryColor=#FF4B4B） | spec-driven（既存コード analog なし・UI-SPEC が正） |
| `tests/ui/__init__.py` | test（パッケージ化） | — | `tests/ev/__init__.py` | exact（慣例） |
| `tests/ui/test_csv_columns.py` | test（unit・presence assert） | — | `tests/ev/test_run_backtest_e2e.py::test_report_columns_present`（L300-324・LOW-05 presence assert） | exact（同一検証パターンの再利用） |
| `tests/ui/test_readonly_guarantee.py` | test（contract・AST/grep） | — | `tests/test_raw_immutability.py`（不変性 grep 検証の既存慣例）+ RESEARCH §Code Examples（L498-538） | role-match（grep/AST 保証テスト） |
| `tests/ui/test_csv_export.py` | test（unit・BOM/CRLF） | — | `src/ev/report.py::_atomic_write_text` 経路（`src/model/artifact.py:59`）+ pandas to_csv 慣例 | role-match |
| `tests/ui/test_segment_schema.py` | test（contract・property） | — | `reports/06-segments/*.json`（実ファイル・6軸） | role-match（契約 test） |
| `tests/ui/test_streamlit_api_usage.py` | test（contract・AST） | — | RESEARCH §Common Pitfalls #1（L374-377・selection_mode 引数検証） | spec-driven |

---

## Pattern Assignments

### `src/ui/csv_columns.py`（utility・列 pin DRY・D-04 LOCKED）

**Analog:** `src/ev/report.py::REPORT_COLUMNS`（L41-53）・`src/db/backtest_load.py::BACKTEST_COLUMNS`（L77-116）・`src/model/predict.py::PREDICTION_COLUMNS`（L63-86）

**Imports pattern**（`src/ev/report.py` L26-33・`from __future__` + 標準ライブラリ + プロジェクト内 import）:
```python
from __future__ import annotations
# 定数のみのモジュールなら import は最小。プロジェクト内型参照が必要なら:
# from typing import Any  # 必要に応じて
```

**列定数定義パターン**（`src/ev/report.py` L39-53 を踏襲・tuple[str, ...] で固定順序）:
```python
# report の列契約（LOW-05: report.md 列ヘッダ・report.json comparison_table キーと 1:1）
# run_backtest.py が全 backtest 行（dict）にこれらのキーを埋める。
REPORT_COLUMNS: tuple[str, ...] = (
    "backtest_id",
    "bt_name",
    "odds_policy",
    ...
)
```

**`src/ui/csv_columns.py` が定義すべき内容**（D-04 LOCKED・§16.2 pin・RESEARCH Pitfall 3 で 16 列確定）:
```python
from __future__ import annotations

# OUT-01: 予測CSV（§16.2 pin・20列・原典 行1092-1112 と照合済）
PREDICTION_CSV_COLUMNS: tuple[str, ...] = (
    "race_id", "race_date", "race_start_datetime", "競馬場", "レース番号",
    "horse_id", "horse_name", "枠番", "馬番", "p_fukusho_hit",
    "fukusho_odds_lower", "fukusho_odds_upper", "EV_lower", "EV_upper",
    "recommend_rank",
    "odds_snapshot_policy", "odds_snapshot_at",
    "model_version", "feature_snapshot_id", "prediction_created_at",
)  # 20 列

# OUT-02: backtest CSV（§16.2 原典 行1118-1133 と照合・RESEARCH Pitfall 3 で16列確定）
# CONTEXT.md D-04 の「14列」は初期ドラフト由来の誤記。CLAUDE.md「要件優先」で 16 を正とする。
BACKTEST_CSV_COLUMNS: tuple[str, ...] = (
    "backtest_id", "backtest_strategy_version",
    "train_period", "validation_period", "odds_snapshot_policy",
    "race_id", "horse_id",
    "selected_flag", "stake", "refund_flag", "payout_amount", "profit",
    "fukusho_hit_validated", "recommend_rank", "EV_lower", "EV_upper",
)  # 16 列（「14列」表記は誤り・RESEARCH Pitfall 3）
```

**列順参照元**（`BACKTEST_COLUMNS` は DB DDL 列順・`PREDICTION_CSV_COLUMNS` は§16.2 表示用に馬名等を追加）:
- DB 列順の正: `src/db/backtest_load.py::BACKTEST_COLUMNS`（L77-116・schema.py DDL と 1:1）
- prediction PK 構成: `src/model/predict.py::PK_COLUMNS`（L97・`year, jyocd, kaiji, nichiji, racenum, umaban, kettonum`）

**Error handling / Validation**: `src/ev/report.py` は `generate_report` 内で列を参照するが presence 検証は `tests/ev/test_run_backtest_e2e.py:300-324` に分離。Phase 7 も同様に定数は純粋定義・検証は `tests/ui/test_csv_columns.py` に分離（後述）。

---

### `src/ui/loaders.py`（service・DB/JSON 読込・`@st.cache_data`）

**Analog:** `src/db/connection.py::readonly_cursor`（L66-76）+ `tests/conftest.py`（L33-48・pool fixture）+ `src/ev/odds_snapshot.py`（readonly SELECT 慣例）

**Imports pattern**（`src/db/connection.py` L10-18 + Streamlit キャッシュ）:
```python
from __future__ import annotations
from contextlib import contextmanager
from psycopg import Cursor
from psycopg_pool import ConnectionPool
from src.config.settings import Settings
# Phase 7 追加:
import streamlit as st
import pandas as pd
import json
from pathlib import Path
```

**DB 接続・readonly pool 構築パターン**（`src/db/connection.py` L21-63・role='readonly' で DSN・search_path 解決）:
```python
def make_pool(settings, *, role="readonly", min_size=1, max_size=8) -> ConnectionPool:
    if role == "readonly":
        conninfo = settings.dsn
        search_path = f"{settings.db_schema_raw},public"
    elif role == "etl":
        ...
    return ConnectionPool(conninfo=conninfo, min_size=min_size, max_size=max_size,
                          kwargs={"options": f"-c search_path={search_path}"}, open=True)
```

**readonly cursor context manager**（`src/db/connection.py` L66-76・そのまま再利用可能）:
```python
@contextmanager
def readonly_cursor(pool: ConnectionPool) -> Iterator[Cursor]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur
```

**`@st.cache_data` 適用パターン**（RESEARCH Pattern 2・L266-294・Pitfall 2 で `hash_funcs` 必須を確定）:
```python
# ⚠ Pitfall 2: ConnectionPool を hash_funcs なしで渡すと UnhashableParamError
# 解法 A: hash_funcs={ConnectionPool: id}
from psycopg_pool import ConnectionPool

@st.cache_data(hash_funcs={ConnectionPool: id})
def load_predictions(pool: ConnectionPool, *, date_from, date_to, jyocd_list, rank_list):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT model_version, feature_snapshot_id, odds_snapshot_policy,
                      year, jyocd, racenum, umaban, kettonum, p_fukusho_hit, race_date
                 FROM prediction.fukusho_prediction
                WHERE is_primary = true
                  AND race_date BETWEEN %s AND %s""",
            (date_from, date_to),
        )
        rows = cur.fetchall()
    return rows  # hashable な戻り値でキャッシュ

# 解法 B（より Streamlit 慣用的）: DSN 文字列を渡す（hashable・hash_funcs 不要）
@st.cache_data
def load_predictions_v2(dsn: str, *, date_from, date_to):
    ...
```

**read-only 保証の核心**（D-03・Phase 8 TEST-01 前提）:
- UI 配下は `make_pool(role='readonly')` または `readonly_cursor` のみ使用。`write_cursor` / `make_pool(role='etl')` は `tests/ui/test_readonly_guarantee.py` で AST/grep 検証（後述）。
- `is_primary=true` 絞り必須（Pitfall 5・Phase 6 D-09・主モデル=LightGBM）。
- SQL は psycopg parameterized query（`%s` placeholder）・文字列組み立て禁止（V5 Input Validation・`src/db/prediction_load.py` の `psycopg.sql.SQL`+`Placeholder` パターン踏襲）。

**JSON 読込パターン**（RESEARCH Code Examples L450-456・reports/06-segments/*.json）:
```python
@st.cache_data
def load_segment_json(axis: str) -> dict:
    """reports/06-segments/<axis>.json を読込（stamped・Phase 6 D-10 生成済）。"""
    path = Path("reports/06-segments") / f"{axis}.json"
    if not path.exists():
        return {}  # empty state・UI-SPEC Copywriting で案内
    return json.loads(path.read_text(encoding="utf-8"))
```

**segment JSON スキーマ**（実ファイル `reports/06-segments/year.json` で確認済・全6軸で統一）:
```json
{"axis_name": "year",
 "segments": [{"curve": {"count":[...], "frac_pos":[...], "mean_pred":[...]},
               "scalar": {"ece_quantile":float, "ece_uniform":float,
                          "max_dev_guarded":float, "mce_guarded":float, "n_samples":int},
               "segment_value": "2024"}]}
```

---

### `src/ui/jyocd_map.py`（utility・YAML マッピング読込）

**Analog:** `src/config/code_tables.yaml`（L9-21・入力データ）+ PyYAML 既存依存（`pyproject.toml` L21）

**マッピング定義**（`src/config/code_tables.yaml` L9-21・実データ SELECT DISTINCT で裏取り・01-10 = JRA 10場）:
```yaml
jyocd:
  "01": "札幌"
  "02": "函館"
  ...
  "10": "小倉"
```

**読込パターン（推奨）**:
```python
from __future__ import annotations
from pathlib import Path
import yaml

_CODE_TABLES_PATH = Path("src/config/code_tables.yaml")

def load_jyocd_map() -> dict[str, str]:
    """code_tables.yaml から jyocd→競馬場名マッピングを読込（DRY・UI 側に dict を持たない）。"""
    data = yaml.safe_load(_CODE_TABLES_PATH.read_text(encoding="utf-8"))
    return dict(data["jyocd"])
```

**Convention**: UI 側にハードコード dict を持たない（DRY・`code_tables.yaml` が単一ソース）。`st.multiselect(format_func=)` で表示名変換に使用。

---

### `src/ui/app.py`（component・Streamlit エントリ）

**Analog:** `scripts/run_backtest.py::main`（L1011-1054・entry pattern・Settings/masked DSN/try-finally）+ UI-SPEC Layout Contract（L40-85）

**Imports pattern**（`scripts/run_backtest.py` L38-98 の entry 慣例を踏襲）:
```python
from __future__ import annotations
import logging
from src.config.settings import Settings
from src.db.connection import make_pool, readonly_cursor
import streamlit as st
# プロジェクト内 import は src.* で直接（src/ui/ は src/config, src/db と同パッケージ階層）
from src.ui.csv_columns import PREDICTION_CSV_COLUMNS, BACKTEST_CSV_COLUMNS
from src.ui.loaders import load_predictions, load_backtests, load_segment_json
from src.ui.jyocd_map import load_jyocd_map
```

**Entry pattern**（`scripts/run_backtest.py` L1011-1054・masked DSN ログ・try-finally pool close）:
```python
def main() -> int:
    settings = Settings()
    # T-05-17 / Shared Pattern 8: 生 DSN は絶対に出力しない (masked のみ)
    logger.info("readonly DSN: %s", settings.dsn_masked)
    readonly_pool = make_pool(settings, role="readonly")
    try:
        return _run_pipeline(args=..., readonly_pool=readonly_pool)
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        readonly_pool.close()
```

**Streamlit レイアウト契約**（UI-SPEC L40-85・D-01..D-05 LOCKED・単一ページ + `st.tabs(3)`）:
```python
st.title("Keiba AI v3 — 複勝予測分析")  # UI-SPEC Copywriting・1回のみ

with st.sidebar:  # D-02 主要フィルタ
    date_range = st.date_input("日付範囲", [])  # range
    selected_jyocd = st.multiselect("競馬場", options=..., format_func=jyocd_map.get)
    selected_ranks = st.multiselect("推奨ランク", ["S","A","B","C","D"], default=["S","A","B"])

tab_pred, tab_bt, tab_cal = st.tabs(["予測一覧", "Backtest", "Segment Calibration"])
with tab_pred: render_prediction_tab(...)
with tab_bt:   render_backtest_tab(...)
with tab_cal:  render_calibration_tab(...)
```

**Error handling**（UI-SPEC Copywriting Contract・Error state・V7 Errors & Logging）:
- DB 接続失敗: `st.error("PostgreSQL（keiba_readonly ロール）に接続できません。src/config/ の DSN と PostgreSQL 起動状態を確認してください。")`
- snapshot/JSON 不整合: `st.error("再現性スタンプが欠落しています。この行は Phase 8（Adversarial Audit）の検証対象です。")`（fail-loud）
- **生 DSN/パスワードは `st.error` に含めない**（`Settings().dsn_masked` のみ・MEDIUM #1 / ASVS V8）。

---

### `src/ui/prediction_tab.py`（component・マスター・ディテール）

**Analog:** `scripts/run_backtest.py::_run_main_model_backtest`（L553-766・merge + metrics 構築）+ `src/ev/report.py::_format_comparison_table_md`（L106-135・手動表生成）

**行選択マスター・ディテールパターン**（RESEARCH Pattern 1・L233-260・Pitfall 1 で正引数名確定）:
```python
# ⚠ Pitfall 1: UI-SPEC の `selection="single-row"` は古い API。正しくは selection_mode + on_select。
event = st.dataframe(
    race_list_df,
    selection_mode="single-row",   # "single-row" | "multi-row" | list
    on_select="rerun",             # "ignore" | "rerun"
    hide_index=False,
)
selection = event.selection
rows = selection.get("rows", [])   # list[int]
if rows:
    selected_idx = rows[0]
    selected_race = race_list_df.iloc[selected_idx]
    horse_df = load_horses_for_race(selected_race["race_key"])
    st.dataframe(horse_df, column_config=...)
else:
    st.info("レースを 1 行選択すると各馬の詳細が表示されます。")
```

**数値フォーマット契約**（UI-SPEC Typography・L141・`%.3f` 固定）:
```python
st.column_config.NumberColumn(format="%.3f")  # p_fukusho_hit / EV_lower / EV_upper
```

**推奨ランク色分け**（UI-SPEC Color L162-169・S のみ accent・色弱配慮でラベル併記）:
| Rank | 色 | 閾値 |
|------|----|----|
| S | `#FF4B4B`（accent） | EV≥1.20 |
| A | `#FF8C00` | EV≥1.10 |
| B | `#F1C40F` | EV≥1.05 |
| C | `#7F8C8D` | EV≥1.00 |
| D | `#BDC3C7` | その他 |

**推奨ランク算出**（Data Provenance A5・prediction テーブルは p のみ・`src/ev/ev_rank.py::compute_ev_and_rank` L80 で純粋関数再適用が推奨）:
```python
from src.ev.ev_rank import compute_ev_and_rank
# prediction_df (p_fukusho_hit + odds) → EV_lower/EV_upper/recommend_rank を付与
pred_with_ev = compute_ev_and_rank(pred_df)
```

**CSV ダウンロード**（RESEARCH Code Examples L418-435・`PREDICTION_CSV_COLUMNS` 適用・UTF-8 BOM + CRLF）:
```python
st.download_button(
    label="予測CSVをダウンロード",
    data=build_prediction_csv_bytes(pred_df),
    file_name=f"predictions_{date_from}_{date_to}.csv",
    mime="text/csv",
)
```

**再現性スタンプ inline 表示**（§19.1 聖域・UI-SPEC L231）: `st.columns(5)` + `st.caption` で5スタンプ（`odds_snapshot_policy`/`odds_snapshot_at`/`model_version`/`feature_snapshot_id`/`backtest_strategy_version`）を各予測行に inline 表示。

**⚠ planner 確認事項**（RESEARCH Open Question 1/2・L620-628）:
- `odds_snapshot_at` の取得元（prediction テーブル DDL L59-94 に同名列なし・backtest テーブル L182 にはあり）。`as_of_datetime` 代用か別途保持か planner 確定。
- EV/odds/rank の算出経路（`compute_ev_and_rank` 純粋関数再適用が最もリーク安全）。

---

### `src/ui/backtest_tab.py`（component・honest 注記）

**Analog:** `src/ev/report.py::generate_report`（L176-274・md/json 分離）+ `BACKTEST_COLUMNS`（`src/db/backtest_load.py` L77-116）

**backtest 行データ SELECT 元**（Data Provenance・`backtest.fukusho_backtest`・`is_primary` 絞り不要・backtest_id で識別）:
- DDL: `src/db/schema.py` BACKTEST_TABLE_DDL（L144-・PK 8カラム = backtest_id + RACE_KEY 7）
- 列順: `src/db/backtest_load.py::BACKTEST_COLUMNS`（L77-116）

**honest 注記**（UI-SPEC Copywriting・必須・Pitfall 6）:
```python
st.warning(
    "注意: この backtest の odds 正確性は JODDS オッズ取得完了後に再検証する subject です。"
    "現状の回収率は暫定値であり、確定後に入れ替わる可能性があります。"
)
st.caption("推奨ランクは参考情報であり、購入判断を強制するものではありません（§19.3・実馬券購入はスコープ外）。")
```

---

### `src/ui/calibration_tab.py`（component・Plotly 動的描画）

**Analog:** `reports/06-segments/year.json`（実スキーマ・入力データ）+ RESEARCH Code Examples L440-496

**Plotly Figure 構築パターン**（RESEARCH Code Examples L458-485・curve 重ね描き + 完全予測線）:
```python
import plotly.graph_objects as go

def build_calibration_figure(seg_data: dict) -> go.Figure:
    fig = go.Figure()
    for seg in seg_data.get("segments", []):
        curve = seg["curve"]
        sv = seg["segment_value"]
        n = seg["scalar"].get("n_samples", 0)
        label = f"{sv} (n={n:,})"
        fig.add_trace(go.Scatter(
            x=curve["mean_pred"], y=curve["frac_pos"], mode="lines+markers",
            name=label, hovertemplate="予測: %{x:.3f}<br>実測: %{y:.3f}<br>" + label,
        ))
    fig.add_trace(go.Scatter(x=[0,1], y=[0,1], mode="lines",
                             line=dict(dash="dash", color="gray"),
                             name="完全予測", showlegend=False))
    fig.update_layout(
        xaxis_title="予測確率 (mean_pred)", yaxis_title="実測頻度 (frac_pos)",
        xaxis_range=[0,1], yaxis_range=[0,1],
        legend_title=seg_data.get("axis_name", ""),
    )
    return fig

axis = st.selectbox("segment 軸", ("year","month","jyocd","entry_count","ninki","odds_band"))
seg_data = load_segment_json(axis)
if not seg_data:
    st.info("segment データが未生成です。scripts/run_evaluation.py を実行して reports/06-segments/ を生成してください。")
else:
    st.plotly_chart(build_calibration_figure(seg_data), use_container_width=True)
    scalar_rows = [{"segment_value": s["segment_value"], **s["scalar"]} for s in seg_data["segments"]]
    st.dataframe(scalar_rows)
```

**Performance**: `use_container_width=True`・`st.plotly_chart`（`fig.show()` でない）・`@st.cache_data` で JSON 読込をキャッシュ（D-05・UI-SPEC Performance Contract）。

---

### `scripts/run_export_predictions_csv.py` / `scripts/run_export_backtest_csv.py`（route・CLI）

**Analog:** `scripts/run_backtest.py`（L36-168・argparse/Settings/masked DSN/output-dir・`KEIBA_SKIP_DB_TESTS` ゲート慣例）

**Imports pattern**（`scripts/run_backtest.py` L38-98・`sys.path.insert` で `src.*` import 可能化）:
```python
from __future__ import annotations
import argparse, logging, sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor  # noqa: E402
from src.ui.csv_columns import PREDICTION_CSV_COLUMNS, BACKTEST_CSV_COLUMNS  # noqa: E402
```

**argparse + Settings + masked DSN パターン**（`scripts/run_backtest.py` L121-168, L1011-1026）:
```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="予測CSV 出力 (OUT-01 / §16.2 pin 20列)")
    parser.add_argument("--output", default="reports/07-predictions.csv")
    parser.add_argument("--date-from", default=None)
    parser.add_argument("--date-to", default=None)
    return parser.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    settings = Settings()
    logger.info("readonly DSN: %s", settings.dsn_masked)  # 生 DSN 絶対禁止
    pool = make_pool(settings, role="readonly")
    try:
        with readonly_cursor(pool) as cur:
            cur.execute("SELECT ... FROM prediction.fukusho_prediction WHERE is_primary = true AND ...", (...))
            ...
        Path(args.output).write_text(csv_text, encoding="utf-8-sig")  # BOM
    finally:
        pool.close()
```

**CSV bytes 生成**（RESEARCH Code Examples L418-427・pandas `to_csv` UTF-8 BOM + CRLF）:
```python
def build_prediction_csv_bytes(df: pd.DataFrame) -> bytes:
    missing = [c for c in PREDICTION_CSV_COLUMNS if c not in df.columns]
    assert not missing, f"予測 DataFrame に必須列がない: {missing}"
    ordered = df[list(PREDICTION_CSV_COLUMNS)]
    return ordered.to_csv(index=False, encoding="utf-8-sig",
                          lineterminator="\r\n").encode("utf-8-sig")
```

**Convention**: UI と CLI は同一の `PREDICTION_CSV_COLUMNS`/`BACKTEST_CSV_COLUMNS` を import（D-04 DRY・列揺れ構造的排除）。reports/ への出力は `src/model/artifact.py::_atomic_write_text`（L59）の atomic write を再利用検討。

---

### `pyproject.toml`（修正・2箇所）

**Analog:** 既存 `pyproject.toml`（同一ファイル編集）

**修正1: dependencies に `streamlit` 追加**（L10-26・`plotly>=6.8.0` と同列）:
```toml
dependencies = [
    ...
    "plotly>=6.8.0",
    "streamlit==1.58.0",   # 追加（CLAUDE.md 推奨・RESEARCH Standard Stack）
    ...
]
```

**修正2: wheel packages に `src/ui` 追加**（L32-33・`src/config`, `src/db` と同列）:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/config", "src/db", "src/ui"]   # src/ui 追加
```

**Installation**（RESEARCH Standard Stack L105-108）: `uv add streamlit==1.58.0`（`uv.lock` 更新・`uv sync --frozen` で再現性担保）。

---

### `.streamlit/config.toml`（新規・spec-driven）

**Analog なし**（UI-SPEC Color/Theme Contract が正）。UI-SPEC L27-29 に従い light theme + accent 色:

```toml
[theme]
base = "light"
primaryColor = "#FF4B4B"
# その他は Streamlit 既定（secondaryBackgroundColor・backgroundColor 等は上書きしない）
```

---

### `tests/ui/test_csv_columns.py`（test・LOW-05 presence assert 再利用）

**Analog:** `tests/ev/test_run_backtest_e2e.py::test_report_columns_present`（L300-324・LOW-05 presence assert パターン）

**LOW-05 presence assert パターン**（`tests/ev/test_run_backtest_e2e.py` L300-324・grep 否定でなく in で存在検証）:
```python
def test_report_columns_present(tmp_path):
    """LOW-05: REPORT_COLUMNS の全要素が report 出力に含まれる (presence 検証)"""
    ...
    report_columns = json_data["constants"]["REPORT_COLUMNS"]
    for row in json_data["comparison_table"]:
        for col in report_columns:
            assert col in row, f"comparison_table 行に {col!r} キーがない (LOW-05 presence 違反)"
    ...
    for col in report_columns:
        assert col in header_line, f"md ヘッダ行に列 {col!r} がない (LOW-05)"
```

**`tests/ui/test_csv_columns.py` が検証すべき内容**（RESEARCH Pattern 3・L320-334・Pitfall 3 で16列確定）:
```python
from src.ui.csv_columns import PREDICTION_CSV_COLUMNS, BACKTEST_CSV_COLUMNS

def test_prediction_csv_columns_count():
    """OUT-01: PREDICTION_CSV_COLUMNS は §16.2 pin の20列である（presence assert）。"""
    assert len(PREDICTION_CSV_COLUMNS) == 20

def test_prediction_csv_has_all_stamps():
    """再現性スタンプ5列が含まれる（§19.1 聖域）"""
    for stamp in ("odds_snapshot_policy", "odds_snapshot_at",
                  "model_version", "feature_snapshot_id"):
        assert stamp in PREDICTION_CSV_COLUMNS, f"再現性スタンプ {stamp} がない"

def test_backtest_csv_columns_count():
    """OUT-02: BACKTEST_CSV_COLUMNS は §16.2 原典の16列（「14列」表記は誤り・Pitfall 3）"""
    assert len(BACKTEST_CSV_COLUMNS) == 16
    assert "backtest_strategy_version" in BACKTEST_CSV_COLUMNS
```

---

### `tests/ui/test_readonly_guarantee.py`（test・AST/grep 構造的検証）

**Analog:** `tests/test_raw_immutability.py`（不変性 grep 検証の既存慣例）+ RESEARCH Code Examples L498-538

**read-only 保証テストパターン**（RESEARCH Code Examples L518-537・AST で `make_pool` の role 引数検証）:
```python
import ast
from pathlib import Path

UI_DIR = Path("src/ui")

def test_ui_has_no_write_ddl_sql():
    """src/ui/ 配下に書き込み/DDL SQL キーワードが含まれない（read-only 違反・D-03）"""
    for py in UI_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        lower = text.lower()
        for kw in ("insert into", "update ", "delete from", "truncate ",
                   "create table", "drop table", "alter table"):
            assert kw not in lower, f"{py}: 書き込み/DDL SQL '{kw}' が含まれる（D-03 違反）"

def test_ui_uses_only_readonly_pool():
    """src/ui/ の make_pool 呼出は全て role='readonly'（既定）または引数なし"""
    for py in UI_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "make_pool":
                role_arg = next((kw.value for kw in node.keywords if kw.arg == "role"), None)
                if role_arg is not None:
                    assert (isinstance(role_arg, ast.Constant) and role_arg.value == "readonly"), \
                        f"{py}: make_pool(role=...) が 'readonly' でない（D-03 違反）"
```

**Phase 8 TEST-01 前提**: このテストが green であることが対抗的監査（書き込み経路不存在）の出発点。

---

### `tests/ui/test_segment_schema.py`（test・property/contract）

**Analog:** `reports/06-segments/*.json`（実ファイル 6軸・入力データ契約）

**検証内容**（RESEARCH Validation Architecture L681・全6軸ファイル走査）:
```python
import json
from pathlib import Path

SEGMENTS_DIR = Path("reports/06-segments")
AXES = ("year", "month", "jyocd", "entry_count", "ninki", "odds_band")
REQUIRED_CURVE_KEYS = {"count", "frac_pos", "mean_pred"}
REQUIRED_SCALAR_KEYS = {"ece_quantile", "ece_uniform", "max_dev_guarded",
                        "mce_guarded", "n_samples"}

def test_all_axes_present():
    """D-12: 6軸全ての JSON が存在する"""
    for axis in AXES:
        assert (SEGMENTS_DIR / f"{axis}.json").exists(), f"{axis}.json が未生成"

def test_segment_schema_contract():
    """全6軸 JSON が axis_name + segments[] (curve/scalar/segment_value) 構造"""
    for axis in AXES:
        data = json.loads((SEGMENTS_DIR / f"{axis}.json").read_text())
        assert "axis_name" in data
        assert "segments" in data
        for seg in data["segments"]:
            assert REQUIRED_CURVE_KEYS <= set(seg["curve"])
            assert REQUIRED_SCALAR_KEYS <= set(seg["scalar"])
            assert "segment_value" in seg
```

---

## Shared Patterns

### 1. CSV 列 pin DRY + presence assert（LOW-05 再利用・最重要）

**Source:** `src/ev/report.py::REPORT_COLUMNS`（L41-53）+ `tests/ev/test_run_backtest_e2e.py::test_report_columns_present`（L300-324）

**Apply to:** `src/ui/csv_columns.py`（定数定義）・`tests/ui/test_csv_columns.py`（検証）・`scripts/run_export_*.py`（import 元）

```python
# src/ev/report.py L41-53 — 列は tuple[str, ...] で固定順序・コメントで契約明記
REPORT_COLUMNS: tuple[str, ...] = ("backtest_id", "bt_name", "odds_policy", ...)

# tests — presence assert（grep 否定でない・存在を in で検証）
for col in REPORT_COLUMNS:
    assert col in row, f"...キー {col!r} がない (LOW-05 presence 違反)"
```

### 2. read-only DB アクセス（D-03・2ロール DSN・keiba_readonly）

**Source:** `src/db/connection.py::make_pool`（L21-63）+ `readonly_cursor`（L66-76）+ `src/config/settings.py`（L63-90・dsn/dsn_masked）+ `src/db/schema.py::GRANT_READER_SQL`（L234-259・prediction/backtest SELECT GRANT 済・T-04-02）

**Apply to:** `src/ui/loaders.py`・`scripts/run_export_*.py`・全 DB SELECT 経路

```python
# readonly pool 構築（src/db/connection.py L21-63）
pool = make_pool(settings, role="readonly")  # settings.dsn・search_path=public
with readonly_cursor(pool) as cur:
    cur.execute("SELECT ... WHERE is_primary = true AND ...", (params,))  # parameterized
# 生 DSN は絶対にログ出力しない・dsn_masked のみ（src/config/settings.py L82-90）
```

**read-only 保証の多重防御**:
- DB ロール: `keiba_readonly` は SELECT のみ・UPDATE/DELETE/TRUNCATE は `REVOKE_RAW_WRITES_*`（schema.py L296-308）で剥奪済。
- UI 配下に `write_cursor`/`make_pool(role='etl')` 経路なし（`tests/ui/test_readonly_guarantee.py` で AST/grep 検証）。
- schema 修飾 SELECT（`prediction.fukusho_prediction`/`backtest.fukusho_backtest`）は GRANT_READER_SQL（L250-258）で reader に付与済。

### 3. entry pattern（Settings + masked DSN + try-finally pool close）

**Source:** `scripts/run_backtest.py::main`（L1011-1054）・Shared Pattern 8

**Apply to:** `scripts/run_export_*.py`（CLI）・`src/ui/app.py`（Streamlit entry・同等の pool ライフサイクル管理）

```python
settings = Settings()
logger.info("readonly DSN: %s", settings.dsn_masked)  # 生 DSN 絶対禁止
readonly_pool = make_pool(settings, role="readonly")
try:
    ...  # pipeline 本体
finally:
    readonly_pool.close()
```

### 4. `is_primary=true` 絞り（主モデル=LightGBM・Pitfall 5）

**Source:** Phase 6 D-09・`src/db/schema.py` PREDICTION_ADD_IS_PRIMARY_SQL（L109-123）・`src/db/prediction_load.py::set_primary_model`

**Apply to:** 全 prediction SELECT（`src/ui/loaders.py`・`scripts/run_export_predictions_csv.py`）

```sql
-- 22,213行×2モデル = 44,426行が入っているため is_primary=true で主モデル(LightGBM)に絞る
SELECT ... FROM prediction.fukusho_prediction WHERE is_primary = true AND ...
```

### 5. UTF-8 BOM + CRLF CSV（Excel 互換・日本語馬名）

**Source:** RESEARCH Code Examples L418-435・UI-SPEC CSV Export Contract L257

**Apply to:** `src/ui/prediction_tab.py`（`st.download_button` data）・`scripts/run_export_*.py`（ファイル出力）

```python
ordered = df[list(PREDICTION_CSV_COLUMNS)]
csv_bytes = ordered.to_csv(index=False, encoding="utf-8-sig",
                           lineterminator="\r\n").encode("utf-8-sig")
```

### 6. コード表 YAML 単一ソース（DRY・Pitfall: UI 側に dict を持たない）

**Source:** `src/config/code_tables.yaml`（L9-21・jyocd 01-10 実測値）

**Apply to:** `src/ui/jyocd_map.py`・競馬場名表示全般

### 7. pytest fixtures + DB-test skip policy

**Source:** `tests/conftest.py`（L1-50・`KEIBA_SKIP_DB_TESTS` ゲート・`pg_pool`/`readonly_cur`/`write_pool` fixture）

**Apply to:** `tests/ui/` 配下（`tests/ui/conftest.py` は親の fixture を再利用・session scope `pg_pool` で DB pool 共有）

```python
# tests/conftest.py L33-48 — 既存 fixture をそのまま継承
@pytest.fixture(scope="session")
def pg_pool(settings): pool = make_pool(settings, role="readonly"); yield pool; pool.close()
@pytest.fixture
def readonly_cur(pg_pool):
    with pg_pool.connection() as conn, conn.cursor() as cur: yield cur
```

---

## No Analog Found

**全ファイルに既存コード analog あり。** 新規発明は最小化（CLAUDE.md「keep it simple」・§12.1）。

唯一 spec-driven（既存コード analog なし・UI-SPEC/RESEARCH が正）なファイル:
- `.streamlit/config.toml`（Streamlit テーマ設定・UI-SPEC Color Contract が正）
- `tests/ui/test_streamlit_api_usage.py`（RESEARCH Pitfall 1 の `selection_mode` 引数 AST 検証・Streamlit API 契約 test）

これらは RESEARCH/ UI-SPEC の記述を直接実装・検証する（既存コードからの類推でなく仕様が正）。

---

## Metadata

**Analog search scope:**
- `src/`（config, db, ev, model, utils）— 列定数・DB 接続・entry pattern・readonly cursor
- `scripts/`（run_backtest, run_evaluation, run_train_predict）— CLI argparse 慣例
- `tests/`（conftest, ev/, db/, test_raw_immutability）— fixture・presence assert・grep 検証
- `reports/06-segments/` — segment JSON 実スキーマ
- `pyproject.toml` — 依存・wheel packages・pytest 設定

**Files scanned:** 12（report.py, connection.py, backtest_load.py, predict.py, schema.py, settings.py, run_backtest.py, code_tables.yaml, pyproject.toml, conftest.py, test_run_backtest_e2e.py, reports/06-segments/year.json）

**Pattern extraction date:** 2026-06-24

**Planner 確認事項（RESEARCH Open Questions 引継ぎ）:**
1. `odds_snapshot_at` の予測 CSV への取得元（prediction テーブルに同名列なし・A4）
2. EV/odds/rank の予測 CSV 算出経路（`compute_ev_and_rank` 純粋関数再適用が推奨・A5）
3. OUT-02 CSV 列数は **16列**（「14列」は誤記・Pitfall 3・要件§16.2 原典優先）
