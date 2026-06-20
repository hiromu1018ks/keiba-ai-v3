# Phase 5: EV & Backtest - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 20（新規 13 + 変更 7）
**Analogs found:** 20 / 20（全ファイルに既存 analog あり・新規アルゴリズム無し）

> **背景（RESEARCH.md §"Don't Hand-Roll" Key insight より引用）:**
> Phase 5 のリーク防止（BACK-04 odds policy 固定・race_id disjoint・返還 honest 会計）は
> すべて既存プリミティブ（`merge_asof`・`group_split` guard・label フラグ・staging-swap）の
> 組み合わせで実現できる。**新規アルゴリズムは EV/rank 計算（純粋関数）と BT窓ヘルパ
> （date filter + guard）のみ。**

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ev/__init__.py` | module root | — | `src/model/__init__.py` 等 | exact |
| `src/ev/odds_snapshot.py` | service (DB READ + pandas) | request-response / PIT-join | `src/model/baseline.py::fetch_market_data` (DB JOIN) + `merge_asof` 既存利用箇所 | role-match |
| `src/ev/ev_rank.py` | service (pure func) | transform | `src/model/baseline.py::compute_bl1/bl2/bl3` | role-match |
| `src/ev/refund_accounting.py` | service (pure func) | transform | `src/etl/fukusho_label.py` の label フラグ導出 + `baseline.py::_payout_places_from_row` | role-match |
| `src/ev/purchase_simulator.py` | service (pure func) | transform | `src/model/baseline.py::_race_normalize_inverse` (groupby head) | role-match |
| `src/ev/metrics.py` | service (pure func) | transform | `src/model/baseline.py::compute_bl1` (純粋 pandas) | role-match |
| `src/ev/bl3_betting.py` | service (pure func) | transform | `src/model/baseline.py::compute_bl3` + `fetch_market_data` | role-match |
| `src/db/backtest_load.py` | service (DB WRITE) | batch / staging-swap | `src/db/prediction_load.py::_idempotent_load_prediction` | exact |
| `scripts/run_backtest.py` | script (orchestrator entry) | batch | `scripts/run_train_predict.py` | exact |
| `src/utils/group_split.py` (変更) | utility | transform | 同ファイル既存 `race_id_time_series_split` | exact |
| `src/model/data.py::split_3way` (変更) | service | transform | 同関数既存ハードコード部 | exact |
| `src/model/orchestrator.py::train_and_predict` (変更) | orchestrator | batch | 同関数既存 + `src/model/data.py::split_3way` | exact |
| `src/db/schema.py` (変更) | config (DDL) | — | 同ファイル既存 `PREDICTION_TABLE_DDL` / `GRANT_READER_SQL` / `GRANT_ETL_SQL` / `APPLY_ORDER` | exact |
| `src/config/settings.py` (変更) | config | — | 同ファイル既存 `db_schema_prediction` | exact |
| `src/db/connection.py` (変更) | config | — | 同ファイル etl search_path 既存行 | exact |
| `reports/05-backtest.{md,json}` (新規生成) | report | file I/O | `reports/04-eval.{md,json}` + `src/model/evaluator.py` | exact |
| `tests/ev/__init__.py` + `conftest.py` | test fixture | — | `tests/conftest.py` + `tests/model/test_baseline.py` の合成データ | role-match |
| `tests/ev/test_odds_snapshot.py` | test (unit) | — | `tests/utils/test_pit_join.py` + `test_group_split.py` | role-match |
| `tests/ev/test_refund_accounting.py` | test (unit・対抗的) | — | `tests/test_fukusho_label.py` (シナリオ assert) | role-match |
| `tests/ev/test_{ev_rank,purchase_simulator,metrics,bl3_betting}.py` | test (unit) | — | `tests/model/test_baseline.py` | role-match |
| `tests/utils/test_group_split.py` (変更) | test (unit) | — | 同ファイル既存 test | exact |
| `tests/model/test_orchestrator_bt.py` | test (unit) | — | `tests/model/test_orchestrator.py` | role-match |
| `tests/db/test_backtest_load.py` | test (integration) | — | `tests/model/test_prediction_load.py` | exact |

> **注:** `tests/db/` は現状存在しない（DB 統合テストは `tests/model/` に混在・例: `test_prediction_load.py`）。`tests/db/test_backtest_load.py` を新設する場合でも既存パターン（`@pytest.mark.requires_db` + `KEIBA_SKIP_DB_TESTS` skip policy）を継承すること。

---

## Pattern Assignments

### `src/ev/odds_snapshot.py`（service, DB READ + PIT-join）

**Analog:** `src/model/baseline.py::fetch_market_data`（DB JOIN 構造）+ `merge_asof(direction='backward')` 思想（CLAUDE.md §13 プリミティブ）

**模倣対象（`fetch_market_data`・`src/model/baseline.py:462-521`）:**
- readonly_cur を明示的に取る（懸念分離・raw/public schema に SELECT-only）
- PK (year, jyocd, kaiji, nichiji, racenum, umaban) 6 カラムで JOIN・`CAST(int)` で型整列（varchar/int 混在の PK 比較を統一）
- `where_clauses` / `params` の parameterized query 構成（SQL injection 防止）
- 戻り値は `pd.DataFrame(rows, columns=cols)` 形式

```python
# baseline.py:500-516 の JOIN PK 構造（JODDS クエリも同形式・6列 PK + HappyoTime で JOIN）
query = f"""
    SELECT o.year, o.jyocd, o.kaiji, o.nichiji, o.racenum, o.umaban,
           n.kettonum, o.fukuoddslow, o.fukuoddshigh, n.ninki
    FROM raw_everydb2.n_odds_tanpuku o
    LEFT JOIN normalized.n_uma_race n
      ON o.year::int = n.year::int AND o.jyocd = n.jyocd
     AND o.kaiji::int = n.kaiji::int AND o.nichiji = n.nichiji
     AND o.racenum::int = n.racenum::int AND o.umaban::int = n.umaban::int
    {where_sql}
"""
readonly_cur.execute(query, params)
```

**JODDS 側の相違点（新規に書く部分）:**
- テーブルは `n_odds_tanpuku`（確定）でなく `n_jodds_tanpuku`（時系列）+ `n_jodds_tanpukuwaku_head` JOIN（`DataKubun` 判定用・本体テーブルには DataKubun 列が無い・RESEARCH Pitfall 2）
- `HappyoTime`(mmddHHMM) と `HassoTime`(hhmm) を `race_start_datetime` 基準で `pd.Timedelta(minutes=N)` 計算（**HHMM 整数比較は日跨ぎで破綻・RESEARCH Pitfall 1**）
- `DataKubun='1'`(中間) で filter（D-01）
- 時点選択本体は `pd.merge_asof(direction='backward', by='race_key')` で実装（CLAUDE.md §13 プリミティブ・未来リーク構造的に不可・D-02）。`merge_asof` 前提として両フレーム `sort_values()` 必須（CLAUDE.md "Pitfall — sort order"）

```python
# CLAUDE.md §13 PIT プリミティブ（Phase 1-A feature join と同一）・JODDS 時点選択も適用
result = pd.merge_asof(
    cutoff_sorted, jodds_sorted,
    left_on='cutoff_datetime', right_on='happyo_datetime',
    by='race_key', direction='backward',  # ← 未来リーク構造的に不可
)
```

**特殊値処理（RESEARCH §1.1/§1.3・BACK-04 silent fallback 禁止）:**
- `FukuOddsLow` が `----`(発売前取消) / `****`(発売後取消) / `0000`(無投票) → `no_bet` sentinel
- `0999`(99.9倍以上) は odds として有効（`no_bet` でない）
- snapshot 0件 → `no_bet`（§11.3）
- `FukusyoFlag` が `0`(発売なし) / `1`(発売前取消) / `3`(発売後取消) も `no_bet`

---

### `src/ev/ev_rank.py`（service, 純粋関数 transform）

**Analog:** `src/model/baseline.py::compute_bl1` / `compute_bl3`（純粋 pandas 関数）

**模倣対象（`compute_bl1`・`src/model/baseline.py:110-128`）:**
- `pd.Series(np.nan, index=df.index, name=...)` で出力 Series を初期化
- 戻り値に `name` を付与（`p_bl1` 等・ev_rank は `EV_lower`/`EV_upper`/`recommend_rank`）
- `df.copy()` で入力を破壊しない（純粋関数）

**相違点（新規）:**
- EV は直線積 `EV_lower = p × odds_lower`（§11.1）・`pd.Series` 演算
- ランク判定は `df.apply(_rank, axis=1)` で階層的（S→A→B→C→D・RESEARCH §3.2）
- `odds_lower` が `no_bet`(NaN) の行は rank='D'（選択対象外）

```python
# RESEARCH §3.2 の純粋関数構造（baseline.py compute_bl1 と同形式）
def compute_ev_and_rank(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['EV_lower'] = df['p_fukusho_hit'] * df['fuku_odds_lower']
    df['EV_upper'] = df['p_fukusho_hit'] * df['fuku_odds_upper']
    df['recommend_rank'] = df.apply(_rank, axis=1)
    return df
```

---

### `src/ev/refund_accounting.py`（service, 純粋関数 transform）

**Analog:** `src/etl/fukusho_label.py` の label フラグ導出ロジック + `src/model/baseline.py::_payout_places_from_row`

**模倣対象1（label フラグ読み・`src/model/data.py:308-330` の `load_labels` SELECT）:**
- `label.fukusho_label` の既存フラグ（`is_scratch_cancel` / `is_race_excluded` / `is_dead_loss` / `is_race_cancelled` / `is_fukusho_sale_available` / `fukusho_payout_places` / `fukusho_hit_validated`）を消費（Phase 2 実装済み・READ のみ・変更なし）
- backtest は label フラグを一次ソース・HARAI は cross-check（RESEARCH §2.3・Pitfall A6）

**模倣対象2（行ベース決定・`baseline.py::_payout_places_from_row:96-104`）:**
```python
# 行の優先列 → fallback 推定のパターン（refund_accounting も同形式）
def _payout_places_from_row(row: pd.Series) -> int:
    if ("fukusho_payout_places" in row.index
            and not pd.isna(row.get("fukusho_payout_places"))
            and int(row["fukusho_payout_places"]) > 0):
        return int(row["fukusho_payout_places"])
    return _payout_places(row["sales_start_entry_count"])
```

**相違点（新規）:**
- `determine_stake_payout(row)` は §11.6 決定表（RESEARCH §2.2）を dict で返す
- label フラグ優先 → HARAI（`FuseirituFlag2`/`TokubaraiFlag2`/`HenkanFlag2`/`PayFukusyoPay`）で payout 確定
- `is_dead_loss`（競走中止）は `effective_stake=100`（loss・§10.6 除外禁止・**RESEARCH Pitfall 4**）
- `_lookup_payfukusyo_pay` は `PayFukusyoUmaban1..5` slot → `PayFukusyoPay1..5` の lookup（同着で slot 2-5 使用）

```python
# RESEARCH §2.3 の決定表実装（label フラグ一次・HARAI cross-check）
def determine_stake_payout(row: pd.Series, stake_per_bet: int = 100) -> dict:
    if not row.get('is_fukusho_sale_available', False):
        return {'stake': 0, 'refund': 0, 'payout': 0, 'profit': 0, 'effective_stake': 0}
    # 返還系（effective_stake=0）
    if (row.get('is_scratch_cancel') or row.get('is_race_excluded')
            or row.get('is_race_cancelled') or row.get('fuseirituflag2') == '1'):
        return {'stake': stake_per_bet, 'refund': stake_per_bet,
                'payout': 0, 'profit': 0, 'effective_stake': 0}
    # 競走中止（§10.6 除外禁止・effective_stake=100）
    if row.get('is_dead_loss'):
        return {'stake': stake_per_bet, 'refund': 0,
                'payout': 0, 'profit': -stake_per_bet, 'effective_stake': stake_per_bet}
    payout = _lookup_payfukusyo_pay(row)
    return {'stake': stake_per_bet, 'refund': 0,
            'payout': payout, 'profit': payout - stake_per_bet,
            'effective_stake': stake_per_bet}
```

---

### `src/ev/purchase_simulator.py`（service, 純粋関数 transform）

**Analog:** `src/model/baseline.py::_race_normalize_inverse`（race_key groupby + sort・`src/model/baseline.py:134-161`）

**模倣対象（race_key groupby パターン）:**
```python
# baseline.py:150 の groupby(race_key_col) パターン
for race_key, group in df.loc[valid_mask].groupby(race_key_col):
    ...
```

**相違点（新規）:**
- §11.4 `fukusho_ev_v1`: フィルタ（EV≥1.05 / p≥0.15 / odds≥1.5 / 複勝発売あり / `no_bet` 除外）→ レース内 top-2
- top-2 は `groupby('race_key').head(2)` で実装（RESEARCH §4.2）
- タイブレーク: `sort_values(['race_key','EV_lower','umaban'], ascending=[True,False,True], kind='mergesort')`（決定論・seed 非依存・RESEARCH §4.3）

```python
# RESEARCH §4.2 の groupby head パターン（baseline._race_normalize_inverse と同形式）
eligible = eligible.sort_values(
    ['race_key', 'EV_lower', 'umaban'], ascending=[True, False, True]
)
selected = (
    eligible.groupby('race_key', group_keys=False)
    .head(max_bets_per_race)  # top-2
)
```

---

### `src/ev/metrics.py`（service, 純粋関数 transform）

**Analog:** `src/model/baseline.py::compute_bl1`（純粋 pandas 関数）

**相違点（新規）:**
- §11.6 回収率 = `sum(payout) / sum(effective_stake)`・`effective_stake=0` は分母から控除（RESEARCH §8.2・Pitfall 5）
- max drawdown: `race_date` 昇順で累積 profit の `cummax - cumsum`（RESEARCH §8.2）
- `effective_stake` 合計 0 のゼロ除算は `0.0` を返す（RESEARCH §8.3）

```python
# RESEARCH §8.2 の累積 drawdown 計算
df_sorted = df.sort_values(['race_date', 'race_key', 'umaban'])
cumulative = df_sorted['profit'].cumsum()
running_max = cumulative.cummax()
drawdown = running_max - cumulative
max_drawdown = int(drawdown.max())
```

---

### `src/ev/bl3_betting.py`（service, 純粋関数 transform）

**Analog:** `src/model/baseline.py::compute_bl3` + `fetch_market_data`（確定オッズ参照）

**模倣対象1（`fetch_market_data`・`src/model/baseline.py:462-521`）:**
- BL-3 は確定オッズ（`n_odds_tanpuku.fukuoddslow`）を使用（JODDS でない・§14.2 市場参照）
- `fetch_market_data(readonly_cur, year=...)` をそのまま再利用（変更なし）

**模倣対象2（`compute_bl3`・`src/model/baseline.py:184-201` + `BL3_COMPARISON_CAVEAT:63-66`）:**
- BL-3 は §14.2 同一情報条件ではない注記を付与（`BL3_COMPARISON_CAVEAT` 定数を再利用）
- BL-3 は p=1/odds で EV 自己参照=1.0 になるため **EV でなく人気順等で選ぶ**（D-04）

**相違点（新規）:**
- `select_bl3_bets(market_df)`: `fukuoddslow` 昇順（低い=人気が高い）で top-2（RESEARCH §9.2）
- `model_type='bl3'`・`odds_snapshot_policy='confirmed'` sentinel で区別（JODDS 時点非依存・RESEARCH §9.3）
- BL-3 は 20 backtest 行列に含まれず・別途 5窓（BT-1..5）×1 = 5 backtest

```python
# RESEARCH §9.2 の確定オッズ昇順 top-2（baseline.compute_bl3 の逆数正規化でなく odds 直接順序）
eligible = eligible.sort_values(
    ['race_key', 'fukuoddslow', 'umaban'], ascending=[True, True, True]
)
selected = eligible.groupby('race_key', group_keys=False).head(max_bets_per_race)
```

---

### `src/db/backtest_load.py`（service, DB WRITE・staging-swap idempotent）

**Analog:** `src/db/prediction_load.py::_idempotent_load_prediction`（model_version スコープ staging-swap）

**模倣対象（`prediction_load.py:174-348` の11ステップ構造）:**

| Step | `prediction_load.py` での実装 | `backtest_load.py` での相違 |
|------|------------------------------|------------------------------|
| 0 | `SELECT pg_advisory_xact_lock(hashtext('prediction.fukusho_prediction'))` | key を `'backtest.fukusho_backtest'` に変更 |
| 1 | 空入力 `RuntimeError`（CR-04(a)） | 同一 |
| 2 | model_version 単一性 assert | **`backtest_id` 単一性 assert**（`{bt_name}-{policy}-{model_type}`・RESEARCH §7.4） |
| 3 | `CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction_staging (LIKE ... INCLUDING ALL)` | staging 名を `backtest.fukusho_backtest_staging` に変更 |
| 4 | `TRUNCATE staging` | 同一 |
| 5 | `executemany INSERT INTO staging` | 同一（列は BACKTEST_COLUMNS） |
| 6 | `SELECT count(*) FROM staging` rowcount verify（WR-06） | 同一 |
| 7 | `DELETE FROM 本テーブル WHERE model_type=%s AND model_version=%s` | **`DELETE FROM backtest.fukusho_backtest WHERE backtest_id=%s`**（backtest_id スコープ・他 backtest_id 行は保持） |
| 8 | `INSERT INTO 本テーブル SELECT cols FROM staging`（明示的列リスト・wild-card 禁止） | 同一 |
| 9 | `DROP TABLE staging` | 同一 |
| 10 | `md5(string_agg(...))` checksum（ORDER BY PK 11・WHERE model_type+model_version scope） | checksum の ORDER BY は backtest PK（backtest_id + RACE_KEY 7 + α）・WHERE backtest_id scope |

**核心的なコード構造（`prediction_load.py:295-307` のスコープ DELETE）:**

```python
# prediction_load.py:295-307 の model_version スコープ DELETE → backtest は backtest_id スコープ
write_cur.execute(
    SQL("DELETE FROM {} WHERE {} = {}").format(
        Identifier("backtest", "fukusho_backtest"),
        Identifier("backtest_id"),
        Placeholder(),
    ),
    (backtest_id,),
)
```

**Imports パターン（`prediction_load.py:52-61` を踏襲）:**

```python
from __future__ import annotations
from typing import Any
import pandas as pd
from psycopg import Cursor
from psycopg.sql import SQL, Identifier, Placeholder
from src.config.settings import Settings
# src/model/predict.py の PREDICTION_COLUMNS 相当 → backtest 側は BACKTEST_COLUMNS を本モジュールで定義
```

**DF→tuple 変換（`prediction_load.py:108-166` の `_df_to_prediction_tuples` パターン）:**
- `_is_na(v)` ヘルパ（pandas/numpy NaN 判定・`prediction_load.py:96-105`）を複製
- 列順は BACKTEST_COLUMNS（schema.py の DDL 列順と 1:1・`predict.py::PREDICTION_COLUMNS` と同一規約）
- 型変換: date/datetime/bool/int/float/str の判別（`fukusho_label.py:1048-1087` と同一パターン）

**公開 API（`prediction_load.py:356-394` の薄い wrapper パターン）:**

```python
def load_backtest(write_cur: Cursor, backtest_df: pd.DataFrame, *,
                  reader_role: str | None = None) -> str:
    if reader_role is None:
        reader_role = Settings().db_reader_role
    rows = _df_to_backtest_tuples(backtest_df)
    return _idempotent_load_backtest(write_cur, rows, reader_role=reader_role)
```

---

### `scripts/run_backtest.py`（script, orchestrator entry）

**Analog:** `scripts/run_train_predict.py`（Phase 4 エントリポイント）

**模倣対象1（起動フロー・`run_train_predict.py:218-411`）:**
1. `Settings()` から `dsn_masked` / `etl_dsn_masked` をログ出力（**生 DSN 絶対禁止・T-04-27**）
2. readonly pool + etl pool 構築（`make_pool(role='readonly'|'etl')`）
3. `try / except PsycopgError / finally pool.close()`（`run_train_predict.py:405-411`）
4. `sys.path.insert(0, _REPO_ROOT)`（`run_train_predict.py:59-61`）で `src.*` import

**模倣対象2（_REPO_ROOT 解決・`run_train_predict.py:59-61`）:**

```python
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
```

**模倣対象3（logging 設定・`run_train_predict.py:84-88`）:**

```python
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_backtest")
```

**模倣対象4（idempotent verify・`run_train_predict.py:367-388`）:**
- 各 backtest_id の `load_backtest` を2回連続実行し checksum bit-identical を検証
- 不一致は `return 3`（run_label_etl.py パターン）

**模倣対象5（reports 出力・`run_train_predict.py:490-570` の `_write_eval_report`）:**
- `reports/05-backtest.md` + `reports/05-backtest.json` を生成（Phase 4 の `04-eval.{md,json}` と対称）
- 全候補一括報告（**winner 単独報告禁止・BACK-04・RESEARCH §10.2**）

**相違点（新規）:**
- BT窓再学習ループ（D-03）: `for bt in BT_WINDOWS: for model_type in [...]: train_and_predict(split_periods=...)`
- フル行列 backtest: 5窓 × 2policy × 2model + 5 BL-3 = 25 backtest
- `split_periods` を `train_and_predict` に注入（後述の orchestrator 拡張経由）
- `--check-reproduce` は BT窓でも固定 seed=42 + `FIXED_REPRODUCE_TS` で bit-identical 保証（`orchestrator._assert_deterministic` を BT窓版に拡張）

```python
# run_train_predict.py:298-317 のモデルループ → BT窓二重ループに拡張
for bt in BT_WINDOWS:
    for model_type in ['lightgbm', 'catboost']:
        calib_start, calib_end = _carve_calib_from_train_tail(bt)
        periods = {
            'train': (bt.train_start, _minus_1day(calib_start)),
            'calib': (calib_start, calib_end),
            'test':  (bt.test_start, bt.test_end),
        }
        result = train_and_predict(
            feature_df, model_type=model_type,
            feature_snapshot_id=args.snapshot_id,
            split_periods=periods,  # 新規パラメータ
            as_of_datetime=FIXED_REPRODUCE_TS,
        )
```

---

### `src/utils/group_split.py`（変更・追記のみ）

**Analog:** 同ファイル既存 `race_id_time_series_split`（`src/utils/group_split.py:29-129`）

**模倣対象1（docstring/handle のリーク防止ガード・`group_split.py:104-127`）:**

```python
# 既存の3ガード（HIGH #2/#3・python -O で生存・raise ValueError 形式）
# ガード1: race_id disjoint
if not set(train_rids).isdisjoint(set(test_rids)):
    raise ValueError(...)
# ガード2: strict chronological（等値不可）
train_time_max = rid_to_time.loc[train_rids].max()
test_time_min = rid_to_time.loc[test_rids].min()
if not (train_time_max < test_time_min):
    raise ValueError(...)
# ガード3: non-empty
if len(train_rids) == 0 or len(test_rids) == 0:
    raise ValueError(...)
```

**模倣対象2（mlxtend re-export・`group_split.py:26`）:**

```python
from mlxtend.evaluate import GroupTimeSeriesSplit  # noqa: F401  (re-exported)
```

**相違点（新規追記・既存関数は変更なし）:**
- `BTWindow` dataclass（frozen=True・`name`/`train_start`/`train_end`/`test_start`/`test_end`/`window_type`）
- `BT_WINDOWS` 定数リスト（§15.5 完全準拠・BT-1..3 expanding / BT-4/5 rolling・**§15.5 の 2019-06 開始を Phase 3 D-09 の 2016H2 より優先・CLAUDE.md「要件定義書優先」**）
- `get_bt_race_ids(races, bt) -> tuple[list[str], list[str]]`（race_date filter + 既存3ガードと同一構造の `raise ValueError`）

```python
# RESEARCH §5.3 の BT窓ヘルパ（既存 guard と同一形式・raise ValueError）
def get_bt_race_ids(races: pd.DataFrame, bt: BTWindow) -> tuple[list[str], list[str]]:
    train = races[races['race_date'].between(bt.train_start, bt.train_end)]
    test  = races[races['race_date'].between(bt.test_start, bt.test_end)]
    train_ids = set(train['race_id']); test_ids = set(test['race_id'])
    if not train_ids.isdisjoint(test_ids):
        raise ValueError(f"{bt.name}: race_id leak across train/test")
    if train['race_start_datetime'].max() >= test['race_start_datetime'].min():
        raise ValueError(f"{bt.name}: strict chronological violated")
    return sorted(train_ids), sorted(test_ids)
```

**注意（既存 docstring の制約・`group_split.py:42-46`）:**
既存 `race_id_time_series_split` の docstring に「本関数は expanding-window のみを生成する。BT-* helper は Phase 4 で追加予定（実際は Phase 5 で追加）」と明記済み。Phase 5 はこの docstring の言及通り BT窓ヘルパを新設する。

---

### `src/model/data.py::split_3way`（変更・後方互換拡張）

**Analog:** 同関数既存ハードコード部（`src/model/data.py:502-575`）

**模倣対象1（既存ハードコード・`data.py:521-524`）:**

```python
train  = frame[frame["race_date"].between("2016-07-01", "2023-12-31")].copy()
calib  = frame[frame["race_date"].between("2024-01-01", "2024-06-30")].copy()
test   = frame[frame["race_date"].between("2024-07-01", "2024-12-31")].copy()
holdout = frame[frame["race_date"] >= "2025-01-01"].copy()
```

**模倣対象2（完全時系列条件 guard・`data.py:540-552`・review MEDIUM#5）:**

```python
# raise ValueError 形式（python -O で生存・HIGH #3）
train_max = train["race_date"].max(); calib_min = calib["race_date"].min()
calib_max = calib["race_date"].max(); test_min = test["race_date"].min()
test_max  = test["race_date"].max()
if not (train_max < calib_min < calib_max < test_min <= test_max):
    raise ValueError("split_3way: 完全時系列条件違反 ...")
```

**模倣対象3（正準 race_key pairwise disjoint guard・`data.py:554-568`・review HIGH#9）:**

```python
train_keys = set(train["race_key"]); calib_keys = set(calib["race_key"])
test_keys  = set(test["race_key"])
for a_name, a_keys, b_name, b_keys in (
    ("train", train_keys, "calib", calib_keys),
    ("train", train_keys, "test",  test_keys),
    ("calib", calib_keys, "test",  test_keys),
):
    overlap = a_keys & b_keys
    if overlap:
        raise ValueError(f"split_3way: {a_name} と {b_name} の正準 race_key が disjoint でない ...")
```

**相違点（新規・後方互換）:**
- `periods: dict[str, tuple[str, str]] | None = None` パラメータを追加（RESEARCH §6.2）
- `periods=None` の場合は既存ハードコードを使用（**Phase 4 回帰防止・A5・SC#4 bit-identical**）
- `periods` 指定時は BT窓（train/calib/test）で `frame.between(*periods[key])` に切替
- 既存の完全時系列条件 guard + race_key disjoint guard はそのまま継承（BT窓でも同一保証）

```python
# RESEARCH §6.2 の後方互換拡張
def split_3way(
    frame: pd.DataFrame,
    *,
    periods: dict[str, tuple[str, str]] | None = None,  # 新規・None なら既存ハードコード
) -> dict[str, pd.DataFrame]:
    if periods is None:
        periods = {
            'train': ('2016-07-01', '2023-12-31'),
            'calib': ('2024-01-01', '2024-06-30'),
            'test':  ('2024-07-01', '2024-12-31'),
        }
    train  = frame[frame["race_date"].between(*periods['train'])].copy()
    calib  = frame[frame["race_date"].between(*periods['calib'])].copy()
    test   = frame[frame["race_date"].between(*periods['test'])].copy()
    # 以降は既存の guard ロジックをそのまま継承（review MEDIUM#5 / HIGH#9）
    ...
```

---

### `src/model/orchestrator.py::train_and_predict`（変更・パラメータ追加）

**Analog:** 同関数既存（`src/model/orchestrator.py:154-452`）+ `split_3way` 拡張（前述）

**模倣対象1（`split_3way` 呼出・`orchestrator.py:246`）:**

```python
# 既存: split_3way(feature_df) を引数なしで呼出
splits = split_3way(feature_df)
```

**相違点（新規・後方互換）:**
- `split_periods: dict[str, tuple[str, str]] | None = None` パラメータを追加
- `split_3way(feature_df, periods=split_periods)` に伝播（`orchestrator.py:246` の1行変更）
- 既定値 `None` で既存の Phase 4 挙動を維持（**A5・後方互換**）

```python
# orchestrator.py:154 シグネチャ拡張（既存パラメータは全て保持・新規 split_periods を末尾に追加）
def train_and_predict(
    feature_df: pd.DataFrame,
    *,
    model_type: str,
    feature_snapshot_id: str,
    version_n: int = 1,
    seed: int = 42,
    eval_fraction: float = 0.2,
    params_override: dict[str, Any] | None = None,
    as_of_datetime: datetime | None = None,
    split_periods: dict[str, tuple[str, str]] | None = None,  # 新規・Phase 5 BT窓用
) -> dict[str, Any]:
    ...
    splits = split_3way(feature_df, periods=split_periods)  # 1行変更
    ...
```

**`_assert_deterministic`（`orchestrator.py:615-666`）の拡張:**
- BT窓でも `split_periods` を渡して bit-identical 検証（seed=42 + 固定 thread + `FIXED_REPRODUCE_TS`）
- 既存の Phase 4 検証（`split_periods=None`）は維持（後方互換）

---

### `src/db/schema.py`（変更・DDL + GRANT + APPLY_ORDER 追加）

**Analog:** 同ファイル既存 `PREDICTION_TABLE_DDL` / `GRANT_READER_SQL` / `GRANT_ETL_SQL` / `APPLY_ORDER`

**模倣対象1（`PREDICTION_TABLE_DDL`・`schema.py:61-96`）:**

```python
# 既存 PREDICTION_TABLE_DDL の構造（provenance NOT NULL + PK RACE_KEY 7 + CHECK 制約 + COMMENT）
PREDICTION_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS prediction.fukusho_prediction (
    -- provenance（§19.1 再現性・NOT NULL）
    model_type varchar(16) NOT NULL,
    model_version varchar(64) NOT NULL,
    feature_snapshot_id varchar(64) NOT NULL,
    as_of_datetime timestamp NOT NULL,
    calib_method varchar(16) NOT NULL,
    -- PK（label.fukusho_label と同一7カラム RACE_KEY + kettonum = horse_id 原列）
    year int, jyocd varchar(2), kaiji int, nichiji varchar(2),
    racenum int, umaban int, kettonum int,
    -- 予測値
    p_fukusho_hit double precision NOT NULL,
    -- 補助メタ
    race_date date, split varchar(16),
    PRIMARY KEY (model_type, model_version, feature_snapshot_id, as_of_datetime,
                 year, jyocd, kaiji, nichiji, racenum, umaban, kettonum),
    CONSTRAINT prediction_fukusho_hit_range CHECK (p_fukusho_hit >= 0 AND p_fukusho_hit <= 1),
    CONSTRAINT prediction_model_type_domain CHECK (model_type IN ('lightgbm','catboost','logreg')),
    CONSTRAINT prediction_calib_method_domain CHECK (calib_method IN ('isotonic','sigmoid'))
);
"""
```

**模倣対象2（GRANT_READER_SQL・`schema.py:128-148`）:**

```python
# 既存 prediction スキーマ GRANT（reader）の3行セット・backtest も同形式で追記
GRANT USAGE ON SCHEMA prediction TO {reader};
GRANT SELECT ON ALL TABLES IN SCHEMA prediction TO {reader};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction GRANT SELECT ON TABLES TO {reader};
```

**模倣対象3（GRANT_ETL_SQL・`schema.py:166-171`）:**

```python
# 既存 prediction スキーマ GRANT（etl）の3行セット・backtest も同形式で追記
GRANT USAGE, CREATE ON SCHEMA prediction TO {etl};
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA prediction TO {etl};
ALTER DEFAULT PRIVILEGES IN SCHEMA prediction
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
```

**模倣対象4（APPLY_ORDER・`schema.py:205-216`）:**

```python
# 既存: prediction_table DDL は grant_reader の直前に挿入（CREATE SCHEMA で prediction
# スキーマ自体は既に作成済・GRANT が GRANT SELECT ON ALL TABLES で本テーブルを拾えるように）
APPLY_ORDER = [
    ("create_schemas", CREATE_SCHEMAS_SQL),   # SCHEMAS には既に "backtest" 含まれる
    ("create_roles",   CREATE_ROLES_SQL),
    ("create_raw_views", CREATE_RAW_VIEWS_SQL),
    ("prediction_table", PREDICTION_TABLE_DDL),  # 既存
    ("backtest_table", BACKTEST_TABLE_DDL),       # 新規挿入（grant_reader の直前）
    ("grant_reader", GRANT_READER_SQL),
    ("grant_etl",    GRANT_ETL_SQL),
    ("revoke_raw_writes_public", REVOKE_RAW_WRITES_PUBLIC_SQL),
    ("revoke_raw_writes_view",   REVOKE_RAW_WRITES_VIEW_SQL),
]
```

**相違点（新規）:**
- `BACKTEST_TABLE_DDL`: backtest_id（複合キー `{bt_name}-{policy}-{model_type}`）を PK 先頭に追加（RESEARCH §7.3）
- provenance 列（`backtest_strategy_version` / `odds_snapshot_policy` / `train_period_start/end` / `test_period_start/end` / `model_type` / `model_version` / `feature_snapshot_id`）
- 選択・会計列（`selected_flag` / `stake` / `refund_flag` / `refund_amount` / `payout_amount` / `profit` / `effective_stake`）
- 的中・rank・EV 列（`fukusho_hit_validated` / `recommend_rank` / `EV_lower` / `EV_upper`）
- odds provenance（`odds_snapshot_at` / `odds_source_type` / `odds_missing_reason`・§11.2）
- CHECK 制約: `model_type IN ('lightgbm','catboost','bl3')`（BL-3 含む・RESEARCH §7.4）・`backtest_strategy_version = 'fukusho_ev_v1'`
- **BL-3 の model_type='bl3'** を CHECK 制約に含める（model_version は sentinel `'bl3_market_v1'` 等）

**`SCHEMAS` 定数（`schema.py:26`）は既に `backtest` を含む**（CREATE SCHEMA のみ・テーブル DDL 無しの状態）→ BACKTEST_TABLE_DDL 追記で完成。

---

### `src/config/settings.py`（変更・フィールド追加）

**Analog:** 同ファイル既存 `db_schema_prediction`（`src/config/settings.py:45`）

**模倣対象（既存 `db_schema_prediction`・`settings.py:42-45`）:**

```python
# Phase 4 prediction schema（D-05・db_schema_label と対称）
# src/db/prediction_load.py の staging-swap idempotent load が
# prediction.fukusho_prediction を schema 修飾で書込む
db_schema_prediction: str = "prediction"
```

**相違点（新規1行追加）:**

```python
# Phase 5 backtest schema（db_schema_prediction と対称・RESEARCH §7.3①）
db_schema_backtest: str = "backtest"
```

---

### `src/db/connection.py`（変更・search_path 1行追加）

**Analog:** 同ファイル既存 etl search_path（`src/db/connection.py:46-50`）

**模倣対象（既存 etl search_path・`connection.py:42-50`）:**

```python
# Phase 2: label スキーマを先頭に追加
# Phase 4: prediction スキーマを label と normalized の間に追加（D-05/D-12）
search_path = (
    f"{settings.db_schema_label},"
    f"{settings.db_schema_prediction},"
    f"{settings.db_schema_normalized},public"
)
```

**相違点（新規1行追加・RESEARCH §7.3②）:**

```python
search_path = (
    f"{settings.db_schema_label},"
    f"{settings.db_schema_prediction},"
    f"{settings.db_schema_backtest},"   # 新規（prediction と normalized の間）
    f"{settings.db_schema_normalized},public"
)
```

---

### `reports/05-backtest.{md,json}`（新規生成・レポート）

**Analog:** `reports/04-eval.{md,json}` + `src/model/evaluator.py`

**模倣対象1（`04-eval.md` の構造）:**
- 比較表（markdown テーブル）・注記セクション・D-04 事前登録基準明記
- `04-eval.md:1` のヘッダ形式: `# Phase 4 Evaluation Report (SC#2 / §15.1 / §15.2)`

**模倣対象2（`04-eval.json` の構造）:**
- `comparison_table`（リスト）+ `metrics`（dict）+ `constants` + `notes` の4セクション
- `notes` に事前登録基準（`d04_selection_criterion`）と market_reference（`bl3_market_reference`）を明記

**相違点（新規）:**
- ヘッダ: `# Phase 5 Backtest Report (BACK-01..04 / §15.5 / §19.1)`（RESEARCH §10.3）
- 比較表: 25 backtest（5窓 × 2policy × 2model + 5 BL-3）を `backtest_id` 順で全件出力
- 列: `backtest_id / bt_name / odds_policy / model_type / recovery_rate / P/L / max_DD / selected / effective_bet / refund / hit_rate`
- §11.2 odds policy 固定の履行確認セクション追加（**BACK-04 構造的ブロック・winner 単独報告禁止・RESEARCH §10.2**）
- `notes` に BL-3 caveat（`baseline.BL3_COMPARISON_CAVEAT` を再利用）・主モデル確定は Phase 6（D-03/D-04）を明記
- 実JODDS取得進行中の場合は「合成データ版 / 取得完了版」の判定を明記（RESEARCH §10.3）

**レポート生成関数（`run_train_predict.py:490-570` の `_write_eval_report` パターン）:**
- 列整列・PK 文字列化（`astype(str)`・`run_train_predict.py:516-523` と同一）して DataFrame → markdown/json 出力

---

### `tests/ev/conftest.py` + `tests/ev/test_*.py`（テスト群）

**Analog:** `tests/conftest.py`（DB fixture・skip policy）+ `tests/model/test_baseline.py`（純粋関数テスト）+ `tests/utils/test_group_split.py`（guard テスト）

**模倣対象1（`tests/conftest.py` の skip policy・HIGH #8）:**
- `KEIBA_SKIP_DB_TESTS=1` の時のみ `@pytest.mark.requires_db` を skip
- デフォルト（CI 含む）は Settings() validation error で fail（fake-green 防止）

**模倣対象2（`tests/utils/test_group_split.py` の guard テスト形式・`test_group_split.py:34-127`）:**

```python
# 既存: raise ValueError を assert（assert でなく raise であることも検証・test_assert_is_replaced_by_raise:115）
def test_race_id_disjoint_raises():
    ...
def test_strict_chronological_per_fold():
    ...
def test_raises_on_missing_columns():
    ...
def test_assert_is_replaced_by_raise():  # python -O で guard が消えないことを検証
    source = inspect.getsource(race_id_time_series_split)
    assert "raise ValueError" in source
```

**模倣対象3（`tests/model/test_prediction_load.py` の integration テスト形式・`test_prediction_load.py:85-206`）:**

```python
# 既存: @pytest.mark.requires_db + write_cur fixture で idempotent verify
@pytest.mark.requires_db
def test_idempotent_checksum_match(write_cur):
    ...

@pytest.mark.requires_db
def test_model_version_scoped_swap_preserves_other_models(write_cur):
    ...
```

**各テストファイルの analog（RESEARCH §1.4/§2.5/§3.4/§4.6/§8.4/§9.4/§5.5/§6.5 より）:**

| Test File | analog | 主要検証内容 |
|-----------|--------|--------------|
| `tests/ev/test_odds_snapshot.py` | `tests/utils/test_pit_join.py` | backward 最近接 / no_bet / special_values / future_leak / day_boundary |
| `tests/ev/test_refund_accounting.py` | `tests/test_fukusho_label.py` | 6シナリオ（通常/取消/除外/中止/不成立/同着）の stake/payout assert |
| `tests/ev/test_ev_rank.py` | `tests/model/test_baseline.py` | EV 計算 / S-D ランク階層判定 |
| `tests/ev/test_purchase_simulator.py` | `tests/model/test_baseline.py` | filter / top2 / tiebreak / no_eligible / no_sale |
| `tests/ev/test_metrics.py` | `tests/model/test_baseline.py` | recovery_rate / max_drawdown / counts |
| `tests/ev/test_bl3_betting.py` | `tests/model/test_baseline.py` | オッズ昇順 top-2 / EV 計算しない / caveat 付与 |
| `tests/utils/test_group_split.py`（変更） | 同ファイル既存 | BT窓 disjoint / chronological / 2019-06 開始 / rolling |
| `tests/model/test_orchestrator_bt.py` | `tests/model/test_orchestrator.py` | split_3way periods injection / 後方互換（periods=None） |
| `tests/db/test_backtest_load.py` | `tests/model/test_prediction_load.py` | idempotent checksum / backtest_id scoped swap |

**合成データ設計（RESEARCH §"Wave 0 Gaps"・実JODDS未完でも検証可能）:**
- JODDS mock: `HappyoTime`(mmddHHMM) 複数 snapshot・`FukuOddsLow` 正常値/特殊値混在
- HARAI mock: `FuseirituFlag2`/`HenkanFlag2`/`PayFukusyoUmaban1..5`/`PayFukusyoPay1..5`
- label mock: `is_scratch_cancel`/`is_dead_loss`/`is_race_cancelled`/`is_fukusho_sale_available`
- prediction mock: p_fukusho_hit + race_key + PK 7カラム

---

## Shared Patterns

### Shared Pattern 1: staging-swap idempotent load（DB WRITE 共通）

**Source:** `src/db/prediction_load.py:174-348`（`_idempotent_load_prediction`）+ `src/etl/fukusho_label.py:945-1019`（`_idempotent_load_label`）

**Apply to:** `src/db/backtest_load.py`

**核心ステップ（11ステップ・同一トランザクション内）:**
```python
# 0. advisory lock（並行 swap 直列化・CR-04(b)）
write_cur.execute(SQL("SELECT pg_advisory_xact_lock(hashtext({}))").format(Placeholder()), (lock_key,))
# 1. 空入力 RuntimeError（CR-04(a)・silent data loss 防止）
if not rows: raise RuntimeError(...)
# 2. scope 単一性 assert（prediction=model_version / backtest=backtest_id）
# 3. CREATE TABLE IF NOT EXISTS staging (LIKE 本テーブル INCLUDING ALL)
# 4. TRUNCATE staging
# 5. executemany INSERT INTO staging
# 6. SELECT count(*) FROM staging → rowcount verify（WR-06）
# 7. scope DELETE from 本テーブル（他 scope 行は保持・silent 履歴破壊防止）
# 8. INSERT INTO 本テーブル SELECT cols FROM staging（明示的列リスト・wild-card 禁止）
# 9. DROP TABLE staging
# 10. md5(string_agg(...)) checksum（ORDER BY PK・WHERE scope）
```

**要注意差分:** `prediction_load.py` は **model_version スコープ DELETE**（他 model_type/version 行を保持）・`fukusho_label.py::_idempotent_load_label` は **全テーブル置換**（DROP + RENAME）。backtest は **backtest_id スコープ DELETE**（prediction_load と同一方針・他 backtest_id 行を保持・RESEARCH §7.4）。

---

### Shared Pattern 2: raise ValueError guard（リーク防止・python -O で生存）

**Source:** `src/utils/group_split.py:104-127` + `src/model/data.py:540-568`

**Apply to:** `src/utils/group_split.py`（BT窓ヘルパ新設分）・`src/model/data.py::split_3way`（periods 拡張分）・`src/ev/odds_snapshot.py`（snapshot 0件/no_bet guard）

**核心（`group_split.py:54-56` の HIGH #3）:**
```python
# assert でなく raise ValueError 形式（python -O で削除されない）
if not (train_time_max < test_time_min):
    raise ValueError(
        f"chronological boundary violated ... (strict < required; §8.4/§15.4/D-17 HIGH #2)"
    )
```

**検証テスト（`tests/utils/test_group_split.py:115-125` のパターン）:**
```python
def test_assert_is_replaced_by_raise():
    source = inspect.getsource(race_id_time_series_split)
    assert "raise ValueError" in source
    assert "assert " not in source  # assert が混入していない
```

---

### Shared Pattern 3: PIT プリミティブ（`merge_asof(direction='backward')`）

**Source:** CLAUDE.md §13 + Phase 1 既存 feature join

**Apply to:** `src/ev/odds_snapshot.py`

**核心（CLAUDE.md §13 より引用）:**
```python
# direction='backward' は各観測行に feature_cutoff_datetime 以前の最新値を結合する。
# 未来情報が cutoff を超えることは構造的に不可能。
result = pd.merge_asof(
    observations_sorted, features_sorted,
    on='feature_cutoff_datetime', by='entity_key',
    direction='backward',  # ← 未来リーク構造的に不可
)
```

**前提条件（CLAUDE.md "Pitfall — sort order"）:**
- 両フレームが結合キーで `sort_values()` 済みであること（未ソートは `merge_asof` が raise）
- 単体テストで sortedness を assert（§17.3）

---

### Shared Pattern 4: DB cursor 懸念分離（readonly / etl 二系統）

**Source:** `src/db/connection.py:21-60` + `src/model/data.py:295-334`（`load_labels` readonly_cur 明示）

**Apply to:** `src/ev/odds_snapshot.py`（readonly_cur で JODDS/HARAI SELECT）・`scripts/run_backtest.py`（readonly + etl pool 使い分け）

**核心（`connection.py:37-52`）:**
```python
if role == "readonly":
    conninfo = settings.dsn
    search_path = f"{settings.db_schema_raw},public"
elif role == "etl":
    conninfo = settings.etl_dsn
    search_path = (
        f"{settings.db_schema_label},"
        f"{settings.db_schema_prediction},"
        f"{settings.db_schema_backtest},"   # Phase 5 追加
        f"{settings.db_schema_normalized},public"
    )
```

**raw read-only / normalized+label+prediction+backtest 書込:** backtest 書込は etl ロールのみ（readonly は REVOKE 済み・`schema.py:179-191`）。

---

### Shared Pattern 5: parameterized SQL query（SQL injection 防止）

**Source:** `src/model/baseline.py:488-517`（`fetch_market_data`）

**Apply to:** `src/ev/odds_snapshot.py`（JODDS/HARAI クエリ）

**核心（`baseline.py:488-494`）:**
```python
where_clauses: list[str] = []
params: list[Any] = []
if year is not None:
    where_clauses.append("o.year = %s")
    params.append(str(year))
where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
readonly_cur.execute(query, params)
```

---

### Shared Pattern 6: reports 慣例（md + json・全候補一括報告）

**Source:** `reports/04-eval.{md,json}` + `scripts/run_train_predict.py:490-570`

**Apply to:** `reports/05-backtest.{md,json}`

**核心:**
- markdown は比較表 + 注記セクション（D-04 事前登録基準・BL-3 caveat 等）
- json は `comparison_table`(list) + `metrics`(dict) + `constants` + `notes` の4セクション
- **winner 単独報告禁止（BACK-04・RESEARCH §10.2）**: 全候補を `backtest_id` 順で並べ・「推奨: BT-X」の記述を入れない・主モデル確定は Phase 6（D-03/D-04 事前登録基準）

---

### Shared Pattern 7: 行整列保証（review HIGH#2）

**Source:** `src/model/orchestrator.py:257-274`

**Apply to:** `src/ev/purchase_simulator.py`（race_key groupby 前の整列）・`src/ev/metrics.py`（race_date 昇順の累積計算）

**核心（`orchestrator.py:257-264`）:**
```python
# merge の直前に index equality を assert（不一致は RuntimeError・silent wrong-horse 防止）
if not X_train_full.index.equals(y_train_full.index):
    raise RuntimeError("X_train_full.index != y_train_full.index (review HIGH#2)")
```

**backtest 側の適用:**
- `select_bets` は `sort_values(kind='mergesort')` で安定ソート（pandas default は quicksort・非安定・RESEARCH §4.3）
- `compute_backtest_metrics` は `race_date` 昇順で累積（同日内は `race_key`→`umaban`）

---

## No Analog Found

**該当なし。** 全20ファイル（新規13 + 変更7）に既存 analog が存在する。Phase 5 の新規アルゴリズムは EV/rank 計算（純粋関数）と BT窓ヘルパ（date filter + 既存 guard）のみで・いずれも既存パターンの組み合わせで実現可能（RESEARCH §"Don't Hand-Roll" Key insight）。

---

## Metadata

**Analog search scope:**
- `src/db/`（prediction_load.py・schema.py・connection.py）
- `src/model/`（baseline.py・orchestrator.py・data.py・predict.py）
- `src/etl/`（fukusho_label.py）
- `src/utils/`（group_split.py）
- `src/config/`（settings.py）
- `scripts/`（run_train_predict.py）
- `reports/`（04-eval.{md,json}）
- `tests/`（conftest.py・model/test_baseline.py・model/test_prediction_load.py・utils/test_group_split.py）

**Files scanned:** 14（うち実コード読込 12・reports 2）

**Pattern extraction date:** 2026-06-20

**主要参照（RESEARCH.md 内）:**
- §1 JODDS 時点選択（odds_snapshot.py）
- §2 返還/中止会計決定表（refund_accounting.py）
- §3 EV 計算・推奨ランク（ev_rank.py）
- §4 仮想購入ルール（purchase_simulator.py）
- §5 BT窓ヘルパ（group_split.py 変更）
- §6 BT窓再学習ループ（data.py / orchestrator.py 変更・run_backtest.py）
- §7 backtest 永続化（schema.py / settings.py / connection.py 変更・backtest_load.py）
- §8 回収率計算（metrics.py）
- §9 BL-3 投資ROI（bl3_betting.py）
- §10 全候補一括報告（run_backtest.py レポート生成）
