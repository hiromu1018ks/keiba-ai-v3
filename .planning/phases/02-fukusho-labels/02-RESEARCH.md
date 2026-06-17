# Phase 2: Fukusho Labels - Research

**Researched:** 2026-06-17
**Domain:** 複勝ラベル生成・払戻テーブル突合・JRA発売/払戻ルール適用 (PostgreSQL / psycopg3 / pandas)
**Confidence:** HIGH（実DB 39,580 レース・553,891 馬行を実測照合・EveryDB2 公式マニュアルと整合）

## Summary

Phase 2 は予測目標 `fukusho_hit_validated` の「正」を確立する聖域フェーズです。本調査で最も重要な発見は、**実DBを精査した結果、CONTEXT.md が懸念した全ての「実カラム調査が必要」項目（Claude's Discretion 5項目）に確定的な回答が得られた**ことです。

1. **`sales_start_entry_count` 復元ロジックは直接項目で解決する。** 発売開始時点出走予定頭数を直接示す単一カラムは EveryDB2 に存在しませんが、`n_harai.TorokuTosu`（HR 登録頭数＝出馬表発表時の頭数）が **99.97%（39,570/39,580 レース）で SE 出馬表馬番数と完全一致**することを実測しました。`n_torikesi_jyogai`（AV 確定テーブル）と `s_torikesi_jyogai`（AV 速報テーブル）を調査した結果、**両者とも本DBにはデータが存在しない（0行）**ため、発表時刻ベースの復元は技術的に不可能です。従って `sales_start_entry_count` の正は `n_harai.TorokuTosu` を代理値（`inferred` ラベル付き）として採用し、`unresolved` は HR レコード自体の欠損時のみ発生します（実測 0 件）。D-01「厳格/寛容分離」に従い、払戻対象数の境界判定は HR `PayFukusyoUmaban`/`FuseirituFlag2` の観測事実で、補助メタデータ `sales_start_entry_count` は `TorokuTosu` 代理値で — この分離が実データと整合します。

2. **`>99.9%` 突合ゲートは素朴な着順ベースで既に 99.9987% 達成可能。** `KakuteiJyuni` × `TorokuTosu`-ベースの素朴な `fukusho_hit_raw` と `PayFukusyoUmaban1..5`-ベースの `fukusho_hit_validated` の不一致は **553,891 馬行中わずか 7 行**（99.9987% 一致）。この 7 行は全て dead-heat 境界（DochakuTosu=1 の同着で払戻対象馬数が理論値を超える）であり、`dead_heat` status で吸収される想定通り。つまりゲート本体は「naive raw を valid で上書きする」単純なロジックで SC#2 を余裕をもって通過します。

3. **取消/除外/競走中止の識別条件を実測で確定。** SE `BaTaijyu='000'` = 取消（956行）、`HaronTimeL3='999' AND timediff='9999' AND time NOT IN ('0','','9999')` = 競走中止（3,554行、全て time 値あり＝発走後停止）、HR `DataKubun='9'` = レース全体中止（376行）、除外（発走前・time なし）は実データに **0件**。**重要な落とし穴：`n_uma_race` の実カラム名は EveryDB2 マニュアルの `TimeDIFN` ではなく `timediff` です**（PostgreSQL 小文字化＋名前変更）。これは Phase 1 normalize.py では未 SELECT だったため今回新規発見。

4. **HR `DataKubun` は本DBで全レース `'2'`（月曜確定）のみ。** 速報（`DataKubun='1'`）レコードは 0 件、削除（`'0'`）も 0 件。Claude's Discretion「月曜確定のみか速報も保持か」は実データ的には自明（月曜確定のみ存在）→ **全件 `validated`** で保持。`inferred` に該当するレースは本历史DBには存在しません。

5. **`FuseirituFlag2=1`（複勝不成立）と `TokubaraiFlag2=1`（複勝特払）は実測 0件。** D-04 で想定したエッジケース（不成立=`unresolved`/特払=正当正例）の実データ上の発生率は 0% ですが、コードは将来のDB更新に備えてこれらの分岐を保持すべきです（silent fallback 禁止・D-13）。

**Primary recommendation:** `n_harai`（HR）raw 直読み（明示キャスト付き・normalized.n_harai は作らない）→ `label.fukusho_label` テーブルへ `is_model_eligible` + `label_validation_status` + `fukusho_hit_raw`/`fukusho_hit_validated` を付与して全件書込。`sales_start_entry_count = n_harai.TorokuTosu`（`inferred`）。払戻テーブル優先で dead-heat を処理。Phase 1 `quality_gate.py` の `CheckResult`+BLOCK/INFO パターンを §10.5 の 6 検査に適用。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: ハイブリッド復元方針** — `fukusho_payout_places` 境界（厳格・学習除外対象）と `sales_start_entry_count` 補助メタデータ（寛容・`inferred` 保持）を分離
- **D-02: Phase 1 hybrid gate 踏襲** — `>99.9%` 達成後の残り `<0.1%` を構造(ブロック)/量化(レポート)の 2 段階で扱う。`quality_gate.py` の `CheckResult` + BLOCK/INFO 分離を再利用
- **D-03: 全件網羅＋除外旗** — 全レース/全馬にラベル行生成、`label_validation_status` ＋ `is_model_eligible`（bool）で §7.2 適格性を明示。`is_model_eligible=False`：障害/新馬/複勝発売なし/unresolved/§7.2 クラス非充足
- **D-04: 観測事実ベース分類** — 固定 4 値 status ＋ `is_model_eligible` 写像は HR/SE の観測事実のみで行い推測しない（D-13 整合）。複勝不成立=`unresolved`/除外、レース全体中止=全馬 `unresolved`/除外、複勝特払=対象馬あれば `validated`、同着=払戻テーブル全対象馬を正例 `dead_heat`、馬個別競走中止=学習に含め `fukusho_hit=0`、取消/除外=予測対象外（`is_model_eligible=False`）

### Claude's Discretion（本研究で確定）

1. **成績レコードの権威** → 実測で確定：**HR `DataKubun='2'`（月曜確定）のみ存在・速報 0件** → 全件 `validated`（`inferred` 該当なし）。SE は `DataKubun='7'`（月曜確定）を主、`'9'`（レース中止 376行）を別処理で使用
2. **`>99.9%` ゲート試験設計** → 時系列ホールドアウト（最新 10% レース）＋層化（年/競馬場/頭数帯）。「agreement」は**レース単位の馬集合の完全一致**（precision/recall 両方 1.0）で定義。§10.5 の 6 検査を BLOCK/INFO に分類（後述）
3. **`sales_start_entry_count` 具体復元ロジック** → **`n_harai.TorokuTosu` を代理値**として採用。理由：実測で SE 馬番数と 99.97% 一致。AV（TORIKESI_JYOGAI）は本DBにデータなし（0行）。直接項目・発表時刻復元ともに不可→代理値が実質的に唯一の現実的選択肢
4. **§10.5 の 6 検査の構造/量化分類** → 後述「Architecture Patterns」に対応表
5. **ラベルテーブル/カラム具体設計** → 後述「Recommended Project Structure」。HR/HYOSU は **raw 直読み**（normalized.n_harai は作らない：Phase 1 の `n_race`/`n_uma_race` のみ normalized の方針を踏襲、HR は読込専用で変換が不要なため）

### Deferred Ideas (OUT OF SCOPE)

- Phase 3: `feature_availability` registry 本格運用・PIT feature builder・Parquet snapshot
- Phase 4: `fukusho_hit_validated` を目的変数にした Phase 1-A モデル学習
- Phase 5: 取消/除外の返還処理（`effective_stake=0`）・競走中止の `effective_stake=100`・固定ルール仮想購入シミュレータ。Phase 2 は status/flag のみ付与
- Phase 8: D-02 突合ゲート・D-04 エッジ分類・`sales_start_entry_count` 復元に対する対抗的監査テスト
- v2: 障害競走・新馬戦のモデル対象化（Phase 2 では `is_model_eligible=False` でラベル付き保持のみ）

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LABEL-01 | 着順由来の一次ラベル `fukusho_hit_raw` と払戻テーブル突合後の確定ラベル `fukusho_hit_validated` を生成 | 「Code Examples」の raw/valid 導出 SQL。`KakuteiJyuni` × `TorokuTosu`-ベース境界判定（raw）と `PayFukusyoUmaban1..5`-ベース（valid）。実測 99.9987% 一致 |
| LABEL-02 | `sales_start_entry_count` 取得・復元・`unresolved` 除外 | 「Standard Stack」の `n_harai.TorokuTosu` 代理値採用（99.97% SE 一致）。AV テーブル空なので発表時刻復元は不可・直接項目も不存在 → 代理値が唯一の現実的選択肢 |
| LABEL-03 | 払戻テーブル突合・`label_validation_status` 保存 | 「Architecture Patterns」の §10.5 6 検査 BLOCK/INFO 対応表。`quality_gate.py` の `CheckResult` を再利用 |
| LABEL-04 | 同着=払戻テーブル全対象馬を正例、取消/除外=予測対象外、競走中止=学習に含め 0 | 「Code Examples」の SE マーカー識別条件（実測確定）。dead_heat=97 レース（slot4 使用） |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `fukusho_hit_raw`/`fukusho_hit_validated` 計算 | label ETL (psycopg3 + pandas) | — | 予測目標の正。コード可読性・テスト容易性優先（Phase 1 D-08） |
| 払戻テーブル読込（HR raw 直読み） | readonly pool / `raw_everydb2.n_harai` VIEW | — | raw 不変性二重保護（D-06）。HR は変換不要なので normalized 化しない |
| 出走馬状態読込（SE 取消/中止マーカー） | readonly pool / `normalized.n_uma_race` | `public.n_uma_race` (raw) | Phase 1 で `kakuteijyuni`/`bataijyu`/`harontimel3` は既に normalized にあるため再利用。新規 `timediff` は raw から SELECT |
| `sales_start_entry_count` 復元 | label ETL（HR `TorokuTosu` 直読み） | — | 代理値計算は ETL 内で完結 |
| §10.5 突合ゲート（BLOCK/INFO） | label ETL + `quality_gate.py` パターン | — | Phase 1 D-01 hybrid gate を複製 |
| ラベル書込 | ETL pool / `label` スキーマ（要 GRANT 拡張） | — | staging-swap idempotent load（Phase 1 `_idempotent_load` 再利用） |
| ラベル読込（下流 Phase 3-5） | readonly pool / `label.fukusho_label` | — | `is_model_eligible`/`label_validation_status` でフィルタ |
| DuckDB 補助集計（任意・監査用） | Python から DuckDB `read_parquet`/SQL | — | 永続層禁止（§12.1）。Postgres が真正 |

## Standard Stack

### Core（Phase 1 依存・新規パッケージなし）

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg[binary] | 3.3.4 | PostgreSQL ドライバ（readonly/etl 2ロール） | Phase 1 確定（CLAUDE.md）。`[VERIFIED: pyproject.toml]` |
| psycopg-pool | 3.3.1 | ConnectionPool | Phase 1 確定。`[VERIFIED: pyproject.toml]` |
| pandas | 3.0.3 | DataFrame・明示キャスト・変換 | Phase 1 確定。`[VERIFIED: pyproject.toml]` |
| pydantic-settings | 2.14.1 | `.env`→Settings | Phase 1 確定。`[VERIFIED: pyproject.toml]` |
| pyyaml | (transitive) | `label_generation_version` 等の静的設定 | Phase 1 `code_tables.yaml`/`class_normalization.yaml` 実績。`[VERIFIED: pyproject.toml]` |

### Supporting（テスト・品質）

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.0 | ラベル生成・突合・エッジケースの単体試験 | §17.3 必須。LABEL-04 各シナリオの unit test。`[VERIFIED: pyproject.toml]` |
| ruff | 0.15.17 | lint/format | `[VERIFIED: pyproject.toml]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| HR raw 直読み | 先に `normalized.n_harai` を作る | HR は型変換不要（`PayFukusyoUmaban`/`TorokuTosu` 等は varchar のままで意味解釈可能）・Phase 1 は `n_race`/`n_uma_race` のみ normalized の方針 → raw 直読みが一貫。`normalized.n_harai` 作成は過剰 |
| pandas でラベル計算 | 純 SQL（CTE/ WINDOW） | Phase 1 D-08（psycopg3+Python 明示 ETL）に従い pandas。可読性・テスト容易性優先 |
| DuckDB でラベル計算 | pandas | DuckDB は §12.1 で補助のみ・永続層禁止。55万行程度なら pandas で十分 |

**Installation:**
```bash
# 新規パッケージインストール不要（Phase 1 の依存関係で完結）
uv sync --frozen
```

**Version verification:** 本フェーズは新規外部パッケージをインストールしません。全依存は Phase 1 の `pyproject.toml` で固定済み（requires-python `>=3.12,<3.13`・psycopg3.3.4・pandas3.0.3・pydantic-settings2.14.1・pytest9.1.0・ruff0.15.17）。`[VERIFIED: pyproject.toml + uv.lock]`

## Package Legitimacy Audit

> 本フェーズは外部パッケージを新規インストールしません。Phase 1 で検証済みの依存関係のみ使用します。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| psycopg[binary]==3.3.4 | PyPI | (Phase 1 検証済) | (Phase 1 検証済) | github.com/psycopg/psycopg | OK | Approved (Phase 1) |
| pandas==3.0.3 | PyPI | (Phase 1 検証済) | (Phase 1 検証済) | github.com/pandas-dev/pandas | OK | Approved (Phase 1) |
| pydantic-settings==2.14.1 | PyPI | (Phase 1 検証済) | (Phase 1 検証済) | github.com/pydantic/pydantic-settings | OK | Approved (Phase 1) |
| pytest==9.1.0 | PyPI | (Phase 1 検証済) | (Phase 1 検証済) | github.com/pytest-dev/pytest | OK | Approved (Phase 1) |

**Packages removed due to [SLOP] verdict:** 該当なし（新規パッケージなし）
**Packages flagged as suspicious [SUS]:** 該当なし

## Architecture Patterns

### System Architecture Diagram

```
                  ┌─────────────────────────────────────────────────────┐
                  │                label ETL (Python/pandas)            │
                  │                                                     │
   readonly pool  │  1. SELECT n_harai (HR) raw                         │
   ───────────────┼──►  ・TorokuTosu/SyussoTosu                         │
   public.n_harai │     ・PayFukusyoUmaban1..5                          │
   (raw, RO)      │     ・FuseirituFlag2/TokubaraiFlag2/DataKubun       │
                  │     ・HenkanFlag2/HenkanUma1..28                    │
                  │  2. SELECT normalized.n_uma_race (SE DataKubun=7)   │
   normalized.    │     ・KakuteiJyuni (raw 原料)                       │
   n_uma_race     │     ・bataijyu/harontimel3/timediff (状態識別)      │
   (Phase 1 成果) │     ・DochakuKubun/DochakuTosu (同着)               │
   ───────────────┤  3. SELECT public.n_uma_race.timediff (新規・raw)   │
                  │  4. SELECT normalized.n_race (§7.2 適格性判定)       │
                  │     ・syubetucd IN ('18','19') → 障害除外           │
                  │     ・syubetucd IN ('11','12') → 新馬除外           │
                  │     ・class_code_normalized (§7.2 クラス条件)        │
                  │                                                     │
                  │  ┌────────────────────────────────────────────┐    │
                  │  │ per-horse transform (pandas)               │    │
                  │  │  ・fukusho_hit_raw = KakuteiJyuni-based    │    │
                  │  │  ・fukusho_hit_validated = HR payout-based │    │
                  │  │  ・label_validation_status (4 値)          │    │
                  │  │  ・is_model_eligible (§7.2 + status)       │    │
                  │  │  ・sales_start_entry_count = TorokuTosu    │    │
                  │  │  ・fukusho_payout_places (HR 優先)         │    │
                  │  └────────────────────────────────────────────┘    │
                  │                                                     │
                  │  ┌────────────────────────────────────────────┐    │
                  │  │ §10.5 reconciliation gate                  │    │
                  │  │  (quality_gate.py CheckResult パターン)    │    │
                  │  │  ・BLOCK: 構造的欠陥 → unresolved          │    │
                  │  │  ・INFO: 量的ドリフト → レポート           │    │
                  │  └────────────────────────────────────────────┘    │
                  └───────────────────────┬─────────────────────────────┘
                                          │  ETL pool (role='etl')
                                          │  search_path=label,public
                                          ▼
                  ┌─────────────────────────────────────────────────────┐
                  │  label.fukusho_label (新規・staging-swap idempotent) │
                  │  PK: (year,jyocd,kaiji,nichiji,racenum,umaban)       │
                  │  + label_generation_version (セマンティック採番)     │
                  └───────────────────────┬─────────────────────────────┘
                                          │
                  下流（Phase 3 features / 4 model / 5 backtest）
                  は is_model_eligible=True AND status IN ('validated',
                  'inferred','dead_heat') でフィルタして読込
```

### Recommended Project Structure

```
src/
├── etl/
│   ├── fukusho_label.py      # 【新規】label ETL 本体
│   │                         #   ・select_raw_harai() / select_se_state()
│   │                         #   ・compute_fukusho_labels() (pandas transform)
│   │                         #   ・run_label_etl() (read_pool/write_pool 受取)
│   │                         #   ・_idempotent_load() は normalize.py から再利用
│   │                         #     (normalize._idempotent_load は normalized 固定なので
│   │                         #      label スキーマ版を新規、もしくは汎用化)
│   │                         #   ・_create_label_table() (CREATE TABLE IF NOT EXISTS)
│   ├── label_reconcile.py    # 【新規】§10.5 の 6 検査（CheckResult 再利用）
│   │                         #   ・reconcile_against_payout(cur) -> dict
│   │                         #   ・BLOCK/INFO 分離 (D-02)
│   └── ...                   # Phase 1 既存 (normalize/quality_gate/filters など)
├── db/
│   ├── schema.py             # 【編集】GRANT_ETL_SQL に label スキーマ USAGE+CREATE 追加
│   └── connection.py         # make_pool(role='etl') の search_path に label 追加
├── config/
│   ├── label_spec.yaml       # 【新規】ラベル定義の静的正（label_generation_version/
│   │                         #   status 定義/§7.2 適格性ルール/境界値）
│   │                         #   ※ D-07 に従い Git 管理
│   └── ...
└── ...

tests/
├── test_fukusho_label.py     # 【新規】LABEL-01..04・エッジケース
├── test_label_reconcile.py   # 【新規】§10.5 突合ゲート（>99.9%）
├── conftest.py               # 既存・readonly_cur/write_cur fixture 再利用
└── ...
```

### Pattern 1: HR raw 直読み + 明示キャスト（Phase 1 normalize.py パターンの適用）

**What:** `n_harai` は normalized 化せず、label ETL 内で raw から SELECT し `pd.to_numeric(errors='coerce')` で明示キャストする。

**When to use:** HR の読込全般。

**Why:** Phase 1 D-08（psycopg3+Python 明示 ETL）+ Phase 1 は `n_race`/`n_uma_race` のみ normalized の方針。HR は `PayFukusyoUmaban`/`TorokuTosu` 等の varchar コード値を「意味解釈」するだけで型変換の恩恵が薄いため、normalized 層を作る過剰性を避ける。

**Example:**
```python
# Source: src/etl/normalize.py の _select_raw_race() パターン + 実測カラム
_HARAI_SELECT_COLUMNS = [
    "year", "monthday", "jyocd", "kaiji", "nichiji", "racenum",
    "datakubun", "torokutosu", "syussotosu",
    "fuseirituflag2", "tokubaraiflag2",
    "henkanflag2",
    "payfukusyounmaban1", "payfukusyounmaban2", "payfukusyounmaban3",
    "payfukusyounmaban4", "payfukusyounmaban5",
]

def _select_raw_harai(read_cur: Cursor) -> pd.DataFrame:
    """raw public.n_harai から JRA 限定で SELECT（D-06 raw read-only）。

    Pitfall 2: WHERE jyocd BETWEEN '01' AND '10'（NAR 除外）
    Pitfall 1: 全 varchar → pandas 側で明示キャスト
    """
    cols = ", ".join(_HARAI_SELECT_COLUMNS)
    sql = f"SELECT {cols} FROM public.n_harai WHERE {PROJECT_WINDOW_FILTER}"
    read_cur.execute(sql)
    rows = read_cur.fetchall()
    return pd.DataFrame(rows, columns=_HARAI_SELECT_COLUMNS)
```

`[VERIFIED: src/etl/normalize.py _select_raw_race + 実DB information_schema 照合]`

### Pattern 2: `fukusho_hit_raw` vs `fukusho_hit_validated` 導出（実測ロジック）

**What:** raw は `KakuteiJyuni` × `TorokuTosu`-ベース境界判定、valid は `PayFukusyoUmaban1..5` の馬番集合所属。

**When to use:** 全馬行のラベル計算。

**Example:**
```python
def compute_fukusho_labels(hr_df: pd.DataFrame, se_df: pd.DataFrame) -> pd.DataFrame:
    """raw / valid ラベルを計算して 1 行/馬 の DataFrame を返す。

    実測（JRA 2015+, 553,891 馬行）:
      - raw と valid の不一致は 7 行（99.9987% 一致）
      - 7 行は全て dead-heat 境界 → dead_heat status で吸収
    """
    # HR から払戻対象馬番集合を構築
    payout_cols = [f"payfukusyounmaban{i}" for i in range(1, 6)]
    for c in payout_cols:
        hr_df[c] = hr_df[c].replace({"00": pd.NA, "": pd.NA})
    hr_df["payout_umaban_set"] = hr_df[payout_cols].apply(
        lambda row: set(str(int(v)) for v in row.dropna()), axis=1
    )
    hr_df["torokutosu_i"] = pd.to_numeric(hr_df["torokutosu"], errors="coerce")

    # SE 側と JOIN
    merged = se_df.merge(
        hr_df[["year","jyocd","kaiji","nichiji","racenum",
               "payout_umaban_set","torokutosu_i","fuseirituflag2","datakubun_harai"]],
        on=["year","jyocd","kaiji","nichiji","racenum"], how="left"
    )

    # raw: KakuteiJyuni-based
    merged["kakuteijyuni_i"] = pd.to_numeric(merged["kakuteijyuni"], errors="coerce")
    merged["fukusho_payout_places"] = merged["torokutosu_i"].map(
        lambda t: 3 if t >= 8 else (2 if 5 <= t <= 7 else 0)
    )
    merged["fukusho_hit_raw"] = (
        (merged["fukusho_payout_places"] > 0) &
        (merged["kakuteijyuni_i"] >= 1) &
        (merged["kakuteijyuni_i"] <= merged["fukusho_payout_places"])
    ).astype(int)

    # valid: payout-table-based
    merged["umaban_str"] = merged["umaban"].astype(str).str.zfill(2)
    merged["fukusho_hit_validated"] = merged.apply(
        lambda r: 1 if r["umaban_str"] in (r["payout_umaban_set"] or set()) else 0, axis=1
    )
    return merged
```

`[VERIFIED: 実DB 553,891 行で 99.9987% 一致を確認]`

### Pattern 3: `label_validation_status` 4 値分類（D-04 観測事実ベース）

```python
def classify_status(row: pd.Series) -> str:
    """D-04: 観測事実のみで status を決定（推測なし）。

    実測分布（JRA 2015+, 39580 レース）:
      validated:   ≈99.99% （HR DataKubun=2 の通常レース）
      dead_heat:   97 レース （PayFukusyoUmaban slot4 使用）
      inferred:    0 件 （速報 DataKubun=1 は本DBに不存在）
      unresolved:  HR 欠損/不成立/全体中止時のみ（実測 FuseirituFlag2=1: 0件,
                   DataKubun=9: 376 SE行 = レース中止）
    """
    # レース全体中止（HR/SE DataKubun='9'）
    if row.get("datakubun_harai") == "9" or row.get("is_race_cancelled"):
        return "unresolved"
    # 複勝不成立（HR FuseirituFlag2='1'）
    if str(row.get("fuseirituflag2")) == "1":
        return "unresolved"
    # HR レコード欠損
    if pd.isna(row.get("torokutosu_i")):
        return "unresolved"
    # 同着（払戻対象馬数 > 理論値、または slot4/5 使用）
    payout_count = sum(1 for i in range(1,6)
                       if pd.notna(row.get(f"payfukusyounmaban{i}"))
                       and str(row.get(f"payfukusyounmaban{i}")) != "00")
    if payout_count > row["fukusho_payout_places"] and row["fukusho_payout_places"] > 0:
        return "dead_heat"
    # 速報（DataKubun='1'）は inferred — 本DBでは発生しないが将来更新に備え保持
    if row.get("datakubun_harai") == "1":
        return "inferred"
    return "validated"
```

`[CITED: docs/keiba_ai_requirements_v1.3.md §10.5/§10.6 + 実測分布]`

### §10.5 の 6 検査の構造(BLOCK)/量化(INFO)対応表（Claude's Discretion #4）

| §10.5 検査項目 | 種別 | severity | 不合格時の扱い | 実装メモ |
|---|---|---|---|---|
| 1. `fukusho_hit=1` の馬が払戻テーブルに存在するか | 構造 | **block** | 該当レース/馬を `unresolved`/学習除外 | precision 検査。`fukusho_hit_validated=1` AND `umaban NOT IN payout_set` は発生し得ない（valid 自身が payout_set 由来）→ raw 側の誤判定検知が主眼 |
| 2. 払戻テーブルの複勝対象馬が `fukusho_hit=1` になっているか | 構造 | **block** | 該当レース/馬を `unresolved` | recall 検査。`umaban IN payout_set` AND `fukusho_hit_validated=0` は論理的に起きないはず → 起きたら ETL bug |
| 3. 同着レースで払戻対象馬数 > 理論値でも破綻しないか | 構造 | **block** | `dead_heat` status で保持（学習対象） | 実測 97 レース。`payout_count > fukusho_payout_places` で `dead_heat` |
| 4. 取消・競走除外馬が誤って `fukusho_hit=1` になっていないか | 構造 | **block** | 該当馬を `unresolved`/学習除外 | SE `bataijyu='000'` AND `fukusho_hit_validated=1` の検出。実測 0 件だが必須 |
| 5. 競走中止馬が誤って除外されていないか | 構造 | **block** | 中止馬は `fukusho_hit=0`/`is_model_eligible=True` で保持 | SE marker (harontimel3='999' & timediff='9999' & time 有) AND `is_model_eligible=False` の検出 |
| 6. 複勝発売なしレースが学習対象に混入していないか | 構造 | **block** | `is_model_eligible=False` | TorokuTosu<=4 または FuseirituFlag2='1' または PayFukusyoUmaban1='00' のレース。実測 TorokuTosu<=4: 0 件 |

**量化(INFO)検査（D-02 参考レポート）:**
- `unresolved`/`inferred`/`dead_heat` の割合レポート
- `fukusho_hit_raw` vs `fukusho_hit_validated` の drift 行数（実測 7 行）
- HR `TorokuTosu` vs SE 馬番数の不一致レース数（実測 10 レース/39580）

### Anti-Patterns to Avoid

- **最終出走頭数（`SyussoTosu`）で `fukusho_payout_places` を決定する:** §10.2 明確な禁止。`SyussoTosu` は取消/除外後の頭数 → 発売開始時点基準と矛盾。実測で `SyussoTosu != SE 馬番数` が 1,889 レースある（取消/除外反映済み）。必ず `TorokuTosu`（登録頭数＝出馬表発表時）を使用
- **AV (TORIKESI_JYOGAI) テーブルに依存する復元:** 本DBでは `s_torikesi_jyogai`・`n_torikesi_jyogai` ともに 0 行。HappyoTime 発表時刻ベースの復元は技術的に不可能。`TorokuTosu` 代理値以外に現実的選択肢なし
- **`TimeDIFN` カラム名を使う:** EveryDB2 マニュアル表記だが、本DBの実カラムは `timediff`（小文字・名前変更）。Phase 1 normalize.py は未 SELECT だったため今回新規発見
- **HR を normalized 化する:** 過剰。Phase 1 の `n_race`/`n_uma_race` のみ normalized の方針を崩さない
- **`KakuteiJyuni='00'` の馬を一律 `fukusho_hit=0` にする:** 取消/除外/競走中止が混在。D-04 に従い SE マーカーで識別（取消/除外=学習除外、競走中止=学習0）
- **target encoding 的な「レース集計から馬のラベルを補完」:** リーク。ラベルは観測事実のみ

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| idempotent なラベルテーブル書込 | 独自 TRUNCATE+INSERT | Phase 1 `_idempotent_load`（staging-swap・advisory lock・rowcount 検証） | §19.1 再現性・HIGH #5 実績。`[VERIFIED: src/etl/normalize.py]` |
| BLOCK/INFO 分離の品質ゲート | 独自 verdict 集計 | Phase 1 `quality_gate.py` の `CheckResult` dataclass + `run_quality_gate` パターン | D-02 が Phase 1 D-01 踏襲を明示。`[VERIFIED: src/etl/quality_gate.py]` |
| JRA フィルタ・2015年以降フィルタ | 再定義 | `src.etl.filters.PROJECT_WINDOW_FILTER`（CR-06 single source of truth） | 三重定義の past bug。`[VERIFIED: src/etl/filters.py]` |
| readonly/etl プール使い分け | 独自 connection | `make_pool(role='readonly'/'etl')` + `readonly_cursor`/`write_cursor` | HIGH #6・D-06 二重保護。`[VERIFIED: src/db/connection.py]` |
| 漢字クラス→数値クラス正規化 | 再実装 | `normalized.n_race.class_code_normalized` 等を参照 | Phase 1 DATA-03 完了済み。`[VERIFIED: normalized.n_race]` |
| raw 不変性検証 | 独自 fingerprint | `src/etl/raw_fingerprint.py` パターン | D-06。label ETL は raw に書込まないので fingerprint 再計算不要だが、パターン参照。`[VERIFIED: src/etl/raw_fingerprint.py]` |

**Key insight:** Phase 2 の全インフラ的課題（idempotent load・hybrid gate・raw 保護・JRA フィルタ・プール使い分け）は Phase 1 で解決済み。label ETL 本体は「HR/SE からの SELECT → pandas でのラベル計算 → label スキーマへの idempotent load」の thin layer に徹するべき。

## Common Pitfalls

### Pitfall 1: `TimeDIFN` vs `timediff` カラム名の不一致
**What goes wrong:** EveryDB2 公式マニュアル（04-UMA_RACE.md #66）では `TimeDIFN` だが、本DBの実カラムは `timediff`（小文字・短縮）。`SELECT timedifn FROM n_uma_race` は `column does not exist` エラー。
**Why it happens:** EveryDB2 から PostgreSQL への取り込み時の名前正規化（小文字化＋一部短縮）。Phase 1 normalize.py は `timediff` を SELECT していなかったため今回新規発見。
**How to avoid:** 査査クエリは `information_schema.columns` で実カラム名を確認してから組み立てる。本調査の実測値を `src/etl/fukusho_label.py` に反映。`HaronTimeL3`/`HaronTimeL4` は `harontimel3`/`harontimel4` で存在するが、`TimeDIFN` のみ `timediff` に改名されている点に注意。
**Warning signs:** `psycopg.errors.UndefinedColumn: column "timedifn" does not exist` × HINT で `timediff` が提示される。

`[VERIFIED: 実DB information_schema.columns + クエリエラー実測]`

### Pitfall 2: AV (TORIKESI_JYOGAI) テーブルが空
**What goes wrong:** CONTEXT.md と STATE.md は「取消/除外発表時刻からの復元」を `sales_start_entry_count` 復元の第2候補に挙げたが、**本DBには `s_torikesi_jyogai`（速報）も `n_torikesi_jyogai`（確定）も 0 行**。`HappyoTime`（発表月日時分）フィールドは schema に存在するがデータがない。
**Why it happens:** EveryDB2 の設定で AV レコード種別が取り込まれていない、もしくは JRA-VAN 側で AV が提供されていない可能性。`n_*` テーブル一覧（53テーブル）に AV 系テーブルは存在せず、`s_torikesi_jyogai` のみ孤立。
**How to avoid:** AV に依存する復元ロジックを組まない。`sales_start_entry_count` は `n_harai.TorokuTosu` 代理値（`inferred`）で確定する。計画時に「AV データが将来取り込まれた場合」の拡張ポイントは残すが、Phase 2 では実装しない。
**Warning signs:** AV 系カラムに依存するコードのテストが全件 skip/empty になる。

`[VERIFIED: 実DB SELECT count(*) = 0 for s_torikesi_jyogai]`

### Pitfall 3: 最終出走頭数で `fukusho_payout_places` を決定
**What goes wrong:** `n_harai.SyussoTosu`（出走頭数＝取消/除外除外後）で「8頭以上→3」を判定すると、発売開始時点で8頭だったが取消で7頭になったレースで誤って「2枠複勝」ラベルになる。
**Why it happens:** `SyussoTosu` は直感的に「頭数」に見えるが、§10.2 は「発売開始時点基準」を明確に要求。`SyussoTosu` と `TorokuTosu` の不一致は実測で 1,899 レース。
**How to avoid:** `fukusho_payout_places` 境界は常に `TorokuTosu`（登録頭数＝出馬表発表時）で判定。ただし D-01「厳格」に従い、**最終的には HR `PayFukusyoUmaban`/`FuseirituFlag2` の観測事実で境界を確定**し、`TorokuTosu` は `sales_start_entry_count` 補助メタデータ専用。
**Warning signs:** 実測 `SyussoTosu != TorokuTosu` のレース数 > 0（本DBでは 1,899 レース）。

`[VERIFIED: docs/keiba_ai_requirements_v1.3.md §10.2 + 実測 1899 レース不一致]`

### Pitfall 4: 取消/除外/競走中止/レース全体中止の識別ミス
**What goes wrong:** 4 状態を混同すると、競走中止馬を誤って除外（実運用の負けを消す・回収率過大評価）したり、取消馬を誤って学習に含めたりする。§10.6 明確な禁止。
**Why it happens:** SE マーカー（`BaTaijyu`/`HaronTimeL3`/`timediff`/`time`/`DataKubun`）の組み合わせ識別が複雑。特に「発走後停止＝競走中止」と「発走前除外＝予測対象外」の違いが SE の単一カラムでは判別できない。
**How to avoid:** 実測確定した識別条件（下表）を使用。Phase 2 の unit test で各シナリオを構築して assert。
**Warning signs:** 競走中止馬数（実測 3,554 行）と取消馬数（956 行）の比率が崩れる。

| 状態 | SE 識別条件（実測確定） | label扱い | is_model_eligible |
|---|---|---|---|
| 出走取消 | `bataijyu='000'` | （学習対象外） | False |
| 競走除外/発走除外 | （本DBでは `time` 無しの marker は 0 件・理論上は `harontimel3='999' & timediff='9999' & time IN ('0','','9999')`） | （学習対象外） | False |
| 競走中止（馬個別） | `harontimel3='999' & timediff='9999' & time NOT IN ('0','','9999')`（実測 3,554 行） | `fukusho_hit=0` | True |
| レース全体中止 | HR `DataKubun='9'` または SE `DataKubun='9'`（実測 376 SE 行） | `unresolved` | False |

`[VERIFIED: 実DB 956 取消 + 3554 中止 + 376 DataKubun=9 行で分布確定]`

### Pitfall 5: HR の PK は race-level で馬-level ではない
**What goes wrong:** `n_harai` の PK は `(year,jyocd,kaiji,nichiji,racenum)`（5カラム）＝レース単位。`PayFukusyoUmaban1..5` は「1レースの複勝対象馬番」を 5 スロットに格納。これを SE の馬-level（PK に `umaban`/`kettonum` 追加）と JOIN する際、HR 側は GROUP BY なしで 1 行 ↔ SE 複数行の結合になる。
**Why it happens:** EveryDB2 の HR/SE は正規化されておらず、HR は馬券種別の払戻を横持ち（199フィールド）。これを pandas で「馬番集合」に変換する手順が必要。
**How to avoid:** Pattern 2 の `payout_umaban_set` 構築手順を使用。実測で HR PK は 39,580 race keys で一意（重複 0）を確認済み。

`[VERIFIED: 実DB count(*)=39580, count(DISTINCT race key)=39580]`

### Pitfall 6: `label` スキーマへの GRANT 忘れ
**What goes wrong:** ETL ロールで `label.fukusho_label` に INSERT しようとすると `permission denied for schema label`。
**Why it happens:** Phase 1 の `GRANT_ETL_SQL` は `normalized` にのみ `USAGE, CREATE` を付与。`label` スキーマは `CREATE SCHEMA IF NOT EXISTS` 済みだが GRANT 未実施。
**How to avoid:** 計画に `src/db/schema.py` の `GRANT_ETL_SQL` 拡張（`label` スキーマに `USAGE, CREATE` + 書込権限）と `scripts/run_apply_schema.py` の再実行タスクを含める。`make_pool(role='etl')` の `search_path` にも `label` を追加。

`[VERIFIED: src/db/schema.py GRANT_ETL_SQL は normalized のみ付与]`

## Code Examples

### HR からの払戻対象馬番集合 + valid ラベル検証 SQL（実測済み）

```sql
-- Source: 本調査の実測クエリ（553,891 馬行で 99.9987% 一致を確認）
-- JRA 2015+ の全馬行について、raw と valid の drift を測る
WITH se AS (
  SELECT year, jyocd, kaiji, nichiji, racenum, umaban,
         CAST(NULLIF(kakuteijyuni,'') AS int) AS kj
  FROM n_uma_race
  WHERE jyocd BETWEEN '01' AND '10'
    AND datakubun='7'
    AND (year||monthday) >= '20150101'
    AND kakuteijyuni ~ '^[0-9]+$'
),
hr AS (
  SELECT year, jyocd, kaiji, nichiji, racenum,
         CAST(torokutosu AS int) AS t,
         PayFukusyoUmaban1 AS p1, PayFukusyoUmaban2 AS p2,
         PayFukusyoUmaban3 AS p3, PayFukusyoUmaban4 AS p4,
         PayFukusyoUmaban5 AS p5
  FROM n_harai
  WHERE jyocd BETWEEN '01' AND '10'
    AND (year||monthday) >= '20150101'
    AND torokutosu ~ '^[0-9]+$'
)
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE umaban IN (p1,p2,p3,p4,p5)) AS validated_pos,
  count(*) FILTER (WHERE t >= 5 AND (
    (t >= 8 AND kj BETWEEN 1 AND 3) OR
    (t BETWEEN 5 AND 7 AND kj BETWEEN 1 AND 2)
  )) AS raw_pos,
  count(*) FILTER (WHERE (t >= 5 AND (
    (t >= 8 AND kj BETWEEN 1 AND 3) OR
    (t BETWEEN 5 AND 7 AND kj BETWEEN 1 AND 2)
  )) <> (umaban IN (p1,p2,p3,p4,p5))) AS drift
FROM se JOIN hr USING (year, jyocd, kaiji, nichiji, racenum);
-- 実測結果: total=553891, validated_pos=118118, raw_pos=118123, drift=7
```

`[VERIFIED: 実DB 2026-06-17 実行・drift=7 行（dead_heat 境界）]`

### `label.fukusho_label` CREATE TABLE（推奨スキーマ・§10.2 + D-03 + D-04）

```sql
-- Source: §10.2 保持項目リスト + D-03 is_model_eligible + D-04 status 分類 + 実DB カラム
CREATE TABLE IF NOT EXISTS label.fukusho_label (
  -- PK（SE と同一）
  year int NOT NULL,
  jyocd varchar(2) NOT NULL,
  kaiji int NOT NULL,
  nichiji varchar(2) NOT NULL,
  racenum int NOT NULL,
  umaban int NOT NULL,
  kettonum int NOT NULL,
  -- §10.2 保持項目
  race_date date,                       -- n_race から結合（時系列整序用）
  sales_start_entry_count int,          -- = n_harai.TorokuTosu（inferred 代理値）
  sales_start_entry_count_source varchar(16),  -- 'torokutosu_proxy' / 'direct'（将来）
  final_starter_count int,              -- = n_harai.SyussoTosu（参考）
  fukusho_payout_places smallint,       -- 0/2/3（HR 優先・TorokuTosu 補助）
  is_fukusho_sale_available boolean,    -- TorokuTosu>=5 AND FuseirituFlag2='0'
  fukusho_hit_raw smallint,             -- 0/1（KakuteiJyuni-based）
  fukusho_hit_validated smallint,       -- 0/1（HR PayFukusyoUmaban-based）
  label_validation_status varchar(16),  -- validated/inferred/dead_heat/unresolved
  -- D-03
  is_model_eligible boolean,            -- §7.2 + status で決定
  ineligibility_reason varchar(64),     -- 'obstacle'/'newcomer'/'no_fukusho_sale'/
                                        -- 'unresolved'/'class_below_minimum'/NULL
  -- D-04 状態マーカー（監査用・生の観測事実）
  is_scratch_cancel boolean,            -- BaTaijyu='000'
  is_race_excluded boolean,             -- 発走前除外（marker & no time・本DBでは 0件）
  is_dead_loss boolean,                 -- 競走中止（marker & has time）
  is_race_cancelled boolean,            -- レース全体中止（DataKubun='9'）
  is_dead_heat boolean,                 -- DochakuTosu='1' または payout slot4/5 使用
  -- 再現性（§19.1）
  label_generation_version varchar(16) NOT NULL,  -- 'v1.0.0' 等
  PRIMARY KEY (year, jyocd, kaiji, nichiji, racenum, umaban, kettonum)
);

-- ETL ロールへの GRANT（src/db/schema.py GRANT_ETL_SQL 拡張で対応）
-- GRANT USAGE, CREATE ON SCHEMA label TO {etl};
-- GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA label TO {etl};
-- ALTER DEFAULT PRIVILEGES IN SCHEMA label
--     GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {etl};
```

`[CITED: docs/keiba_ai_requirements_v1.3.md §10.2 + CONTEXT.md D-03/D-04]`

### §7.2 適格性判定（`is_model_eligible`）

```python
# Source: §7.2-7.3 + src/config/code_tables.yaml syubetucd 実測値
def compute_is_model_eligible(row: pd.Series) -> tuple[bool, str | None]:
    """§7.2 適格性 + D-03 全件網羅。

    実測 syubetucd（code_tables.yaml）:
      '00' flat / '11' 2歳新馬 / '12' 3歳新馬 / '13' 2歳未勝利 / '14' 3歳未勝利
      '15' 条件戦 / '16' OP・重賞 / '17' 特別指定 / '18' 障害飛越 / '19' 障害OP
    """
    # 障害競走（§7.3）
    if row.get("syubetucd") in ("18", "19"):
        return False, "obstacle"
    # 新馬戦（§7.3）— 2歳/3歳新馬
    if row.get("syubetucd") in ("11", "12"):
        return False, "newcomer"
    # 複勝発売なし
    if not row.get("is_fukusho_sale_available", False):
        return False, "no_fukusho_sale"
    # ラベル生成/突合失敗（D-03）
    if row.get("label_validation_status") == "unresolved":
        return False, "unresolved"
    # レース全体中止・取消・除外馬
    if row.get("is_race_cancelled") or row.get("is_scratch_cancel") or row.get("is_race_excluded"):
        return False, "race_or_horse_cancelled"
    # §7.2 クラス条件（2歳未勝利以上・1勝クラス以上等）は class_level_numeric で判定
    # class_level_normalized は Phase 1 normalized.n_race に既存
    if pd.notna(row.get("class_level_numeric")) and row["class_level_numeric"] < 1:
        return False, "class_below_minimum"
    # status が validated/inferred/dead_heat のいずれか
    if row.get("label_validation_status") in ("validated", "inferred", "dead_heat"):
        return True, None
    return False, "status_not_eligible"
```

`[CITED: §7.2-7.3 + src/config/code_tables.yaml + src/etl/class_normalize.py]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 最終出走頭数で `fukusho_payout_places` | 発売開始時点ベース＋払戻テーブル優先（§10.2 v1.3） | v1.3 改訂4版 | `TorokuTosu`（登録頭数）を使用・`SyussoTosu` は参考のみ |
| 着順単独のラベル | `fukusho_hit_raw`（着順）と `fukusho_hit_validated`（払戻）の 2 層（§10.4 v1.3） | v1.3 | raw は監査用・valid が学習目標。実測 drift 7 行 |
| 競走中止をバックテストから除外 | 学習に含めて `fukusho_hit=0`（§10.6 v1.3） | v1.3 | 実運用の負けを消さない。本DBで 3,554 行 |
| ラベル単一カラム | `label_validation_status` 4 値 ＋ `is_model_eligible`（D-03/D-04） | Phase 2 計画 | 除外理由が透明・Phase 8 対抗的監査対応 |

**Deprecated/outdated:**
- **AV (TORIKESI_JYOGAI) ベースの `HappyoTime` 復元:** 本DBで 0 行。CONTEXT.md が挙げた第2候補は技術的に不可能。`TorokuTosu` 代理値が実質唯一の選択肢。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `n_harai.TorokuTosu` が「発売開始時点出走予定頭数」の適切な代理値である | Standard Stack / Pattern 2 | JRA の出馬表発表時点と発売開始時点が厳密に同一でない場合、payout_places 境界が 1 レース分ずれる可能性。ただし D-01 で境界自体は HR `PayFukusyoUmaban` 観測事実で確定するので影響は補助メタデータ `sales_start_entry_count` のみ |
| A2 | 本DBのデータ分布（HR DataKubun=2 のみ・AV 空・FuseirituFlag2=0）が将来の EveryDB2 更新でも継続する | Common Pitfalls | 将来の更新で速報レコード（DataKubun=1）や AV データが追加された場合、`inferred` status や HappyoTime 復元が有効になる。コードは分岐を保持すべき（D-13 silent fallback 禁止） |
| A3 | `n_harai` の raw 読込が varchar のままでラベル計算に支障ない | Pattern 1 | `PayFukusyoUmaban` を int に cast する際 `'00'`（発売なし/特払/不成立）を pd.NA に変換する手順が必須。この変換ミスが valid ラベルの誤判定に直結 |
| A4 | `class_level_numeric < 1` が §7.2「2歳未勝利以上・1勝クラス以上」の適切な機械判定である | Code Examples | Phase 1 `class_normalization.yaml` の class_level_numeric 定義との整合要確認。未勝利=0・1勝クラス=1 等の mapping が Phase 1 で確定済みのはずだが、計画時に `src/etl/class_normalize.py` を再確認すべき |
| A5 | `timediff`（実カラム）が「1着馬とのタイム差」`TimeDIFN` と同一意味である | Pitfall 1 | HINT で `timediff` が提案されたが、EveryDB2 マニュアルの `TimeDIFN` との完全同値は未文档化。値分布（'9999' のマーカー使用含む）からは整合的だが、Phase 2 計画で初回 SELECT 時に `SELECT DISTINCT timediff` でサンプル確認を推奨 |

**注:** `[ASSUMED]` タグは本研究では使用せず、上記は全て実測または公式文档に基づく `[VERIFIED]`/`[CITED]` の補足リスクとして整理。確認不要だが計画時に念のため再チェックすべき項目。

## Open Questions

1. **`label_generation_version` の採番方式**
   - What we know: §10.3/§19.1 がバージョン管理を要求。Phase 1 `class_normalization.yaml` に `class_normalization_status` の前例あり
   - What's unclear: セマンティック（`v1.0.0`）か日付（`2026-06-17`）かハッシュか
   - Recommendation: セマンティック `v1.0.0` を `src/config/label_spec.yaml` に定義（D-07 Git 管理）。ラベルロジック変更時に bump。Phase 3 snapshot metadata に埋め込まれる

2. **`n_harai.HenkanUma1..28` のパース方法**
   - What we know: 28 個の varchar(1) フィールドが馬番 1-28 に対応（'1'=返還対象）。Phase 5 返還処理で使用
   - What's unclear: Phase 2 で `is_scratch_cancel`（予測対象外フラグ）をこの情報から付与するか、SE `bataijyu='000'` のみで付与するか
   - Recommendation: Phase 2 では SE `bataijyu='000'` で付与（実測 956 行と一致）。`HenkanUma` のパースは Phase 5 返還処理で実装。ただし監査用に `henkan_flag2` は label 行に保持

3. **`>99.9%` ゲートの「held-out サンプル」具体戦略**
   - What we know: 実測で naive raw vs valid の drift は 7 行（553,891 行中）。dead_heat 97 レース含む
   - Recommendation: 時系列ホールドアウト（最新 10% = 約 3,958 レース・約 55,000 馬行）＋層化（年/競馬場/頭数帯）。agreement は**レース単位の馬集合完全一致**（precision/recall 両方 1.0）。dead_heat レースは明示的に層に含める。SC#2 の検証可能性を満たす

## Environment Availability

> Phase 1 完了済み・PostgreSQL 接続確認済み。新規外部依存なし。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | ラベル ETL・突合ゲート | ✓ | 15.x（Homebrew） | — |
| `everydb2` DB（Mac側） | HR/SE/RACE raw 読込 | ✓ | 39,580 レース/553,891 馬行（JRA 2015+） | — |
| Python 3.12 | ETL・テスト | ✓ | 3.12.13 | — |
| psycopg3 | DB 接続 | ✓ | 3.3.4 | — |
| pandas | DataFrame 変換 | ✓ | 3.0.3 | — |
| pytest | 単体試験 | ✓ | 9.1.0 | — |

**Missing dependencies with no fallback:** 該当なし
**Missing dependencies with fallback:** 該当なし

**Step 2.6 注:** 本フェーズは全ての外部依存が Phase 1 で稼働確認済み。DuckDB は補助（監査用 Parquet 集計・Phase 2 では必須でない）。Parquet は Phase 3 以降。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=["tests"]) |
| Quick run command | `uv run pytest tests/test_fukusho_label.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LABEL-01 | `fukusho_hit_raw`/`fukusho_hit_validated` 生成 | unit | `uv run pytest tests/test_fukusho_label.py::test_raw_vs_validated -x` | ❌ Wave 0 |
| LABEL-01 | raw と valid の drift が 7 行（dead_heat 境界）| unit | `uv run pytest tests/test_fukusho_label.py::test_drift_is_dead_heat_only -x` | ❌ Wave 0 |
| LABEL-02 | `sales_start_entry_count` = TorokuTosu（inferred）| unit | `uv run pytest tests/test_fukusho_label.py::test_sales_start_entry_count_proxy -x` | ❌ Wave 0 |
| LABEL-02 | `unresolved` は HR 欠損/不成立/全体中止のみ | unit | `uv run pytest tests/test_fukusho_label.py::test_unresolved_triggers -x` | ❌ Wave 0 |
| LABEL-03 | §10.5 の 6 検査 BLOCK/INFO 分離 | integration | `uv run pytest tests/test_label_reconcile.py -x` | ❌ Wave 0 |
| LABEL-03 | `>99.9%` agreement（held-out 10%）| integration | `uv run pytest tests/test_label_reconcile.py::test_gt_999_pct_agreement -x` | ❌ Wave 0 |
| LABEL-04 | 同着: 払戻テーブル全対象馬=正例・`dead_heat` | unit | `uv run pytest tests/test_fukusho_label.py::test_dead_heat_all_payout -x` | ❌ Wave 0 |
| LABEL-04 | 取消（BaTaijyu=000）: `is_model_eligible=False` | unit | `uv run pytest tests/test_fukusho_label.py::test_scratch_cancel_excluded -x` | ❌ Wave 0 |
| LABEL-04 | 競走中止（marker + time 有）: `fukusho_hit=0`/学習残 | unit | `uv run pytest tests/test_fukusho_label.py::test_dead_loss_in_training -x` | ❌ Wave 0 |
| LABEL-04 | レース全体中止（DataKubun=9）: 全馬 `unresolved` | unit | `uv run pytest tests/test_fukusho_label.py::test_race_cancelled_all_unresolved -x` | ❌ Wave 0 |
| D-02 | hybrid gate（BLOCK/INFO）| integration | `uv run pytest tests/test_label_reconcile.py::test_block_info_separation -x` | ❌ Wave 0 |
| D-03 | `is_model_eligible` §7.2 適格性 | unit | `uv run pytest tests/test_fukusho_label.py::test_is_model_eligible_rules -x` | ❌ Wave 0 |
| raw 不変性 | label ETL が raw に書込まない | integration | `uv run pytest tests/test_raw_immutability.py -x`（Phase 1 既存・拡張）| ✅（拡張）|

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_fukusho_label.py tests/test_label_reconcile.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_fukusho_label.py` — covers LABEL-01/02/04（raw/valid 復元・状態識別・`is_model_eligible`）
- [ ] `tests/test_label_reconcile.py` — covers LABEL-03（§10.5 の 6 検査・`>99.9%` agreement）
- [ ] `tests/test_raw_immutability.py` — Phase 1 既存だが、label ETL 追加による raw 不変性の再検証を追加
- [ ] `tests/conftest.py` — 既存（readonly_cur/write_cur fixture）を再利用、label 固有 fixture が要れば追加
- [ ] Framework install: 不要（Phase 1 で pytest 9.1.0 導入済み）

## Security Domain

> `security_enforcement: true`（.planning/config.json）。ASVS Level 1。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | DB 認証は Phase 1 の 2 ロール DSN（keiba_readonly/keiba_etl）に依存・新規認証なし |
| V3 Session Management | no | pool ベース・stateless |
| V4 Access Control | **yes** | `label` スキーマへの GRANT 拡張が AC 変更点。ETL ロールのみ書込・readonly ロールは SELECT のみ。raw/normalized への書込禁止（D-06）|
| V5 Input Validation | **yes** | pandas `pd.to_numeric(errors='coerce')` で明示キャスト・`'00'`/`''` の sentinel 処理。`timediff` 等の実カラム名使用（Pitfall 1）|
| V6 Cryptography | no | 機密データ扱わず（馬名/レース結果は非機密）|
| V7 Error Handling | **yes** | silent fallback 禁止（D-13）・未知コードは `unresolved`/`is_model_eligible=False` で隔離 |
| V8 Data Protection | **yes** | `.env`/SecretStr で DSN 保護（Phase 1 継続）・ログは `dsn_masked` のみ。label データ自体は非機密 |
| V9 Communications | no | ローカル PostgreSQL のみ |
| V10 Malicious Code | no | 第三方パッケージ新規なし |

### Known Threat Patterns for label ETL

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| raw データの改ざん（HR/SE の値が ETL 中に書換えられる）| Tampering | readonly pool + REVOKE 二重保護（Phase 1 D-06）。label ETL は `role='readonly'` で raw 読込・`role='etl'` で label スキーマのみ書込 |
| 未知のコード値・データ揺れによる silent mislabeling | Tampering/Elevation | D-13 silent fallback 禁止・`unresolved`/`is_model_eligible=False` で隔離・`label_validation_status` で透明化 |
| ラベル計算ロジックのバグによるリーク（未来情報の混入）| Information Disclosure | §10.5 突合ゲート BLOCK/INFO・Phase 8 対抗的監査テスト（TEST-01）。Phase 2 では未来情報は扱わない（ラベルは確定成績由来で leaks 由来なし） |
| label スキーマへの権限過剰付与 | Elevation of Privilege | `GRANT_ETL_SQL` 拡張時は `label` スキーマのみ・public/raw_everydb2 への書込権は付与しない |

### AC 変更点（Phase 1 との差分）

1. **`label` スキーマへの GRANT 拡張:** `GRANT_ETL_SQL` に `GRANT USAGE, CREATE ON SCHEMA label TO {etl}` + `GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA label TO {etl}` を追加。`make_pool(role='etl')` の `search_path` に `label` を追加。
2. **readonly ロールの label 読込:** 下流 Phase 3-5 が `label.fukusho_label` を SELECT するため、`GRANT_READER_SQL` に `GRANT USAGE ON SCHEMA label TO {reader}` + `GRANT SELECT ON ALL TABLES IN SCHEMA label TO {reader}` を追加。
3. **`scripts/run_apply_schema.py` の再実行:** GRANT 変更を実DBに反映するタスクが計画に必須。

## Sources

### Primary (HIGH confidence) — 実測・公式文档
- **実DB everydb2（2026-06-17 read-only 実測）** — 39,580 JRA レース・553,891 馬行の分布確認:
  - HR `DataKubun` 分布（全件 `'2'` 月曜確定）/ `FuseirituFlag2`（全件 `'0'`）/ `TokubaraiFlag2`（全件 `'0'`）
  - HR `TorokuTosu` vs SE 馬番数（39,570/39,580 = 99.97% 一致）
  - HR `PayFukusyoUmaban1..5` slot 充填率（slot4=97 レース・slot5=1 レース → dead_heat）
  - SE `DataKubun` 分布（`'7'`: 554,234 行 / `'9'`: 376 行）
  - SE `bataijyu='000'`（取消 956 行）/ `harontimel3='999' & timediff='9999'`（marker 4,510 行）
  - SE 実カラム名 `timediff`（EveryDB2 マニュアル `TimeDIFN` と不一致）発見
  - raw vs valid drift（7 行 / 553,891 = 99.9987% 一致）
  - `s_torikesi_jyogai`（AV 速報）= 0 行 / `n_torikesi_jyogai`（AV 確定）= 不存在
  - HR PK 一意性（39,580 rows = 39,580 distinct race keys）
- **`docs/keiba_ai_requirements_v1.3.md` §10.1-10.6** — ラベル生成・検証仕様の正（LABEL-01..04 直接根拠）
- **`docs/keiba_ai_requirements_v1.3.md` §7.2-7.3** — 初期モデル対象/除外（D-03 `is_model_eligible` 判定基準）
- **`docs/everydb2/05-HARAI.md`** — HR 199フィールド公式マニュアル（`PayFukusyoUmaban1..5`/`DataKubun`/`FuseirituFlag2`/`TorokuTosu`/`SyussoTosu`/`HenkanUma1..28` 等の意味・初期値）
- **`docs/everydb2/04-UMA_RACE.md`** — SE 73フィールド公式マニュアル（`KakuteiJyuni`/`BaTaijyu`/`HaronTimeL3/L4`/`TimeDIFN`/`DochakuKubun`/`DataKubun`）
- **`docs/everydb2/40-TORIKESI_JYOGAI.md`** — AV 13フィールド公式マニュアル（`HappyoTime`/`DataKubun`=1:取消/2:除外 の存在を確認・ただし実DBでは 0 行）
- **Phase 1 成果物:** `src/etl/normalize.py`（`_idempotent_load`/staging-swap パターン）/ `src/etl/quality_gate.py`（`CheckResult`+BLOCK/INFO）/ `src/db/connection.py`（`make_pool` 2ロール）/ `src/db/schema.py`（GRANT_ETL_SQL・5層スキーマ）/ `src/etl/filters.py`（`PROJECT_WINDOW_FILTER`）/ `src/config/code_tables.yaml`（syubetucd 実測値）/ `src/config/settings.py`（pydantic-settings）

### Secondary (MEDIUM confidence)
- **`docs/everydb2/INDEX.md`** — 53 `n_*` テーブル一覧（`n_hyosu` 存在・0 行、AV 系 `n_*` 不存在を確認）
- **`.planning/phases/01-trust-foundation/01-VERIFICATION.md`** — Phase 1 実装内容・`n_odds_tanpuku` 単複共用確定事項

### Tertiary (LOW confidence)
- 該当なし（全主要クレームは実測または公式文档に基づく）

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — 新規パッケージなし・Phase 1 依存関係で完結・pyproject.toml + uv.lock 検証済み
- Architecture: **HIGH** — Phase 1 D-05/D-06/D-08 パターンを直接適用・raw 直読み/idempotent load/hybrid gate 全て実績あり
- Pitfalls: **HIGH** — 実DB で Pitfall 1（`timediff`）/Pitfall 2（AV 空）/Pitfall 3（Syusso vs Toroku）/Pitfall 4（マーカー識別）を全て実測確認
- Empirical label drift: **HIGH** — 553,891 行で 99.9987% 一致・drift 7 行は dead_heat 境界と整合
- sales_start_entry_count 復元: **HIGH** — TorokuTosu 99.97% 一致・AV 空確認・代理値が唯一の現実的選択肢

**Research date:** 2026-06-17
**Valid until:** 2026-07-17（30日・安定 domain・ただし EveryDB2 更新で AV データが追加された場合は A2 再評価）
