"""Hybrid Quality Gate（D-01）— everydb2.public.n_* に対する品質ゲート。

01-02-PLAN.md に基づき、構造的欠陥（severity="block"）と量的異常
（severity="info"）を分離して pass/fail verdict を返す。

BLOCK チェック（verdict に影響）:
  - 主要5系統テーブル存在（n_race / n_uma_race / n_harai / n_hyosu / n_odds_tanpuku）
  - JRA 2015-01-01 以降データ存在（成功基準#1）
  - n_race PK 一意（row-tuple ``count(DISTINCT (...))`` 形式・MEDIUM concat-key 衝突回避）
  - n_uma_race 自然キー一意（同上）

INFO チェック（verdict に影響しない・参考レポート）:
  - 主要テーブルの件数（全体 / JRA 限定）
  - min/max(year||monthday)
  - 主要カラムの NULL率・code=0 or 空白の割合
  - 数値カラム（kyori/futan/hassotime）の明示キャスト成功率（Pitfall 1）
  - **mojibake 検出（REVIEWS HIGH #7）:** U+FFFD を含む行数を主要 varchar カラムで報告
  - **code-value anomaly 検出（REVIEWS HIGH #7）:** jyokencd5 / gradecd / jyocd /
    syubetucd が allowed-code-set 外の件数と割合を報告

Pitfall 対策:
  - Pitfall 1（全 varchar）: ``CAST(... AS integer)`` で明示キャストし失敗率を INFO 報告
  - Pitfall 2（NAR 混入）: 全クエリで ``jyocd BETWEEN '01' AND '10'``
  - Pitfall 4（s_*/n_* 取り違え）: 対象は ``n_*``（確定）のみ

セキュリティ（T-02-02）:
  - run_quality_gate の戻り値の各 check dict は ``name/passed/severity/detail`` のみ。
    DSN/password 等の認証情報は一切含めない（``scripts/run_quality_report.py`` が
    allowlist filter で二重防御する）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from psycopg import Cursor

# CR-06: single source of truth — import from src.etl.filters. The module-level
# ``JRA_ONLY_FILTER`` name is kept as a re-export so existing imports/tests do
# not break. New code should import from ``src.etl.filters`` directly.
from src.etl.filters import JRA_FILTER

# JRA 10場限定フィルタ（Pitfall 2）。class_normalization.yaml にも同一値。
# 全ての品質クエリは ``jyocd BETWEEN '01' AND '10'`` で JRA に絞り、NAR 混入
# （jyocd>=30）を排除する。下記 SQL 群の ``{JRA_ONLY_FILTER}`` 展開箇所がこの要件を満たす。
JRA_ONLY_FILTER = JRA_FILTER

# EveryDB2 主要5系統（D-02・plan 01-01 で実測: n_odds_fukusho は存在せず、
# 単複は n_odds_tanpuku 共用テーブルに含まれる）。
TARGET_TABLES = (
    "n_race",
    "n_uma_race",
    "n_harai",
    "n_hyosu",
    "n_odds_tanpuku",
)

# n_race の主キーカラム（row-tuple 形式で一意性検査・MEDIUM concat-key 衝突回避）
N_RACE_PK_COLS = "year, jyocd, kaiji, nichiji, racenum"
# n_uma_race の自然キー（PK + umaban + kettonum）
N_UMA_RACE_NK_COLS = "year, jyocd, kaiji, nichiji, racenum, umaban, kettonum"

# mojibake 検出対象の主要 varchar カラム（実DBで存在を確認済み）。
# plan が挙げた kisyu/torikishi は n_uma_race に無いため、実在する騎手名カラム
# ``kisyuryakusyo`` と調教師名 ``chokyosiryakusyo`` に置換（Rule 3・実DBカラム名優先）。
MOJIBAKE_COLUMNS_N_RACE = ("hondai", "jyokenname")
MOJIBAKE_COLUMNS_N_UMA_RACE = ("bamei", "kisyuryakusyo", "chokyosiryakusyo", "banusiname")

# 明示キャスト検査対象（Pitfall 1: 全 varchar なので数値カラムは明示 CAST が必要）。
# Rule 1: ``futan`` は ``n_uma_race`` 側（馬毎の負担重量）。``n_race`` には存在しない。
# 実検査は ``!~ '^[0-9]+$'`` で安全に件数集計する（``CAST(kyori AS integer)`` の例外安全版）。
CAST_COLUMNS_N_RACE = ("kyori", "hassotime")
CAST_COLUMNS_N_UMA_RACE = ("futan",)

# real（小数）キャスト対象。``futan`` は負担重量 0.1kg 単位で小数値（例 "57.5"）をとる。
# 整数専用 ``'^[0-9]+$'`` ではこれらを実キャスト失敗と誤判定して cast 成功率を破損する
# ため、小数を許容する ``'^[0-9]+(\.[0-9]+)?$'`` で検査する（CR-02）。
REAL_CAST_COLUMNS = {"futan"}

# U+FFFD REPLACEMENT CHARACTER を PostgreSQL escape 文字列リテラルで表記したもの。
# ``U&'\\+00FFFD'`` は PostgreSQL の Unicode escape 文字列定数。
U_FFFD_PG = "U&'\\+00FFFD'"

# src/config/*.yaml のパス（本モジュール基準）
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass
class CheckResult:
    """品質チェック1件の結果。

    Attributes:
        name: チェック名（機械判定用の安定識別子）
        passed: 成功か否か
        severity: ``"block"`` または ``"info"``（D-01）。block が一つでも passed=False
            なら verdict="fail" になる。
        detail: 詳細情報（件数・率・カラム毎の内訳など）。認証情報は絶対に含めない。
    """

    name: str
    passed: bool
    severity: str
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# allowed-code-set 構築（REVIEWS HIGH #7・T-02-04）
# ---------------------------------------------------------------------------


def _load_allowed_codes() -> dict[str, set[str]]:
    """class_normalization.yaml と code_tables.yaml から allowed-code-set を構築する。

    戻り値:
        ``{"jyokencd5": {...}, "gradecd": {...}, "jyocd": {...}, "syubetucd": {...}}``

    これらの許容値セットは静的に決定（D-07 Git 管理）。検査時の silent fallback
    を防ぐため、YAML 読込失敗時は例外を送出する（T-02-01 mitigation）。
    """
    class_yaml_path = _CONFIG_DIR / "class_normalization.yaml"
    code_yaml_path = _CONFIG_DIR / "code_tables.yaml"

    try:
        with class_yaml_path.open(encoding="utf-8") as f:
            class_yaml: dict[str, Any] = yaml.safe_load(f)
        with code_yaml_path.open(encoding="utf-8") as f:
            code_yaml: dict[str, Any] = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        # silent fallback 禁止（T-02-01・T-02-04）: 例外で fail に傾く
        raise RuntimeError(f"failed to load allowed-code config from {_CONFIG_DIR}: {exc}") from exc

    jyokencd5_map = class_yaml.get("jyokencd5_map", {})
    gradecd_map = class_yaml.get("gradecd_map", {})
    jyocd_map = code_yaml.get("jyocd", {})
    syubetucd_map = code_yaml.get("syubetucd", {})

    allowed: dict[str, set[str]] = {
        "jyokencd5": set(str(k) for k in jyokencd5_map.keys()),
        "gradecd": set(str(k) for k in gradecd_map.keys()),
        "jyocd": set(str(k) for k in jyocd_map.keys()),
        "syubetucd": set(str(k) for k in syubetucd_map.keys() if k != "note"),
    }

    # いずれかが空の場合は設定ファイル破損の可能性 → fail-fast
    empty = [k for k, v in allowed.items() if not v]
    if empty:
        raise RuntimeError(f"allowed-code-set が空です（設定ファイル破損の疑い）: {empty}")

    return allowed


# ---------------------------------------------------------------------------
# BLOCK チェック群（severity="block"）
# ---------------------------------------------------------------------------


def _check_table_exists(cur: Cursor, table: str) -> CheckResult:
    """public.<table> が information_schema.tables に存在するか（D-02 主要5系統）。"""
    cur.execute(
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    cnt = int(cur.fetchone()[0])
    return CheckResult(
        name=f"table_exists:{table}",
        passed=cnt > 0,
        severity="block",
        detail={"table": table, "exists": cnt > 0, "matches": cnt},
    )


def _check_jra_since_2015(cur: Cursor) -> CheckResult:
    """JRA かつ 2015-01-01 以降のレース件数が > 0 か（成功基準#1）。

    ``(year||monthday) >= '20150101'`` で日付比較。``year``/``monthday`` は varchar。
    """
    cur.execute(
        """
        SELECT count(*) FROM n_race
        WHERE (year||monthday) >= '20150101'
          AND jyocd BETWEEN '01' AND '10'
        """
    )
    cnt = int(cur.fetchone()[0])
    return CheckResult(
        name="jra_since_2015",
        passed=cnt > 0,
        severity="block",
        detail={"count": cnt, "since": "2015-01-01", "filter": JRA_ONLY_FILTER},
    )


def _check_n_race_pk_unique(cur: Cursor) -> CheckResult:
    """n_race の PK（year, jyocd, kaiji, nichiji, racenum）が JRA 限定で一意か。

    **MEDIUM concat-key 衝突回避:** ``year || jyocd || ...`` のような素の文字列結合ではなく
    ``count(DISTINCT (year, jyocd, ...))`` の row-tuple 形式で理論衝突を回避する。
    """
    cur.execute(
        f"""
        SELECT count(*), count(DISTINCT ({N_RACE_PK_COLS}))
        FROM n_race
        WHERE jyocd BETWEEN '01' AND '10'
        """
    )
    total, distinct = cur.fetchone()
    total = int(total)
    distinct = int(distinct)
    dup = total - distinct
    return CheckResult(
        name="n_race_pk_unique",
        passed=dup == 0,
        severity="block",
        detail={
            "total": total,
            "distinct": distinct,
            "duplicates": dup,
            "pk_cols": N_RACE_PK_COLS,
        },
    )


def _check_n_uma_race_natural_key_unique(cur: Cursor) -> CheckResult:
    """n_uma_race の自然キー（PK + umaban + kettonum）が JRA 限定で一意か（同上）。"""
    cur.execute(
        f"""
        SELECT count(*), count(DISTINCT ({N_UMA_RACE_NK_COLS}))
        FROM n_uma_race
        WHERE jyocd BETWEEN '01' AND '10'
        """
    )
    total, distinct = cur.fetchone()
    total = int(total)
    distinct = int(distinct)
    dup = total - distinct
    return CheckResult(
        name="n_uma_race_natural_key_unique",
        passed=dup == 0,
        severity="block",
        detail={
            "total": total,
            "distinct": distinct,
            "duplicates": dup,
            "nk_cols": N_UMA_RACE_NK_COLS,
        },
    )


# ---------------------------------------------------------------------------
# INFO チェック群（severity="info"）
# ---------------------------------------------------------------------------


def _check_table_counts(cur: Cursor) -> CheckResult:
    """主要5系統テーブルの全体件数と JRA 限定件数を報告（参考）。

    NAR 混入を可視化するため全体と JRA 限定を分けて報告（Pitfall 2）。
    """
    columns: dict[str, dict[str, int]] = {}
    for t in TARGET_TABLES:
        try:
            cur.execute(f"SELECT count(*) FROM {t}")
            total = int(cur.fetchone()[0])
            cur.execute(f"SELECT count(*) FROM {t} WHERE {JRA_ONLY_FILTER}")
            jra = int(cur.fetchone()[0])
        except Exception as exc:  # noqa: BLE001
            columns[t] = {"error": str(exc)}
            continue
        columns[t] = {"total": total, "jra": jra, "non_jra": total - jra}

    return CheckResult(
        name="table_counts",
        passed=True,
        severity="info",
        detail={"columns": columns},
    )


def _check_date_range(cur: Cursor) -> CheckResult:
    """n_race の min/max(year||monthday) を全体と JRA 限定で報告。"""
    columns: dict[str, str] = {}
    try:
        cur.execute("SELECT min(year||monthday), max(year||monthday) FROM n_race")
        lo, hi = cur.fetchone()
        columns["overall_min"] = str(lo)
        columns["overall_max"] = str(hi)
        cur.execute(
            f"SELECT min(year||monthday), max(year||monthday) FROM n_race WHERE {JRA_ONLY_FILTER}"
        )
        jlo, jhi = cur.fetchone()
        columns["jra_min"] = str(jlo)
        columns["jra_max"] = str(jhi)
    except Exception as exc:  # noqa: BLE001
        columns["error"] = str(exc)

    return CheckResult(
        name="date_range",
        passed=True,
        severity="info",
        detail={"columns": columns},
    )


def _check_null_rates(cur: Cursor) -> CheckResult:
    """主要カラムの NULL率 と code=0/空白の割合を報告（参考）。

    Rule 1 修正: ``futan`` は ``n_uma_race`` 側（馬毎の負担重量）であり ``n_race`` には
    存在しない（実DBで確認）。``n_race`` 側は ``kyori`` / ``hassotime`` 等のレース属性。
    ``CAST`` 検査対象と併せてカラムをテーブル毎に正しく振り分け直した。
    """
    # 実DBで存在を確認済み（Rule 1: 元 plan の kisyu/torikishi/futan-on-n_race は誤り）
    table_cols: dict[str, tuple[str, ...]] = {
        "n_race": ("kyori", "hassotime", "jyokencd5", "gradecd", "syubetucd"),
        "n_uma_race": ("umaban", "kettonum", "kakuteijyuni", "bamei", "futan"),
    }
    columns: dict[str, dict[str, float]] = {}

    for table, cols in table_cols.items():
        # 全体件数
        cur.execute(f"SELECT count(*) FROM {table} WHERE {JRA_ONLY_FILTER}")
        total = int(cur.fetchone()[0])
        cols_stat: dict[str, float] = {}
        for c in cols:
            try:
                cur.execute(
                    f"SELECT count(*) FROM {table} WHERE {JRA_ONLY_FILTER} AND ({c} IS NULL)"
                )
                null_cnt = int(cur.fetchone()[0])
                cur.execute(
                    f"""SELECT count(*) FROM {table} WHERE {JRA_ONLY_FILTER}
                        AND ({c} = '0' OR {c} = '')"""
                )
                zero_cnt = int(cur.fetchone()[0])
                null_pct = (null_cnt / total * 100.0) if total else 0.0
                zero_pct = (zero_cnt / total * 100.0) if total else 0.0
                cols_stat[f"{c}_null_pct"] = round(null_pct, 4)
                cols_stat[f"{c}_zero_or_blank_pct"] = round(zero_pct, 4)
            except Exception as exc:  # noqa: BLE001
                cols_stat[f"{c}_error"] = str(exc)  # type: ignore[assignment]
        columns[table] = cols_stat  # type: ignore[assignment]

    return CheckResult(
        name="null_rates",
        passed=True,
        severity="info",
        detail={"columns": columns},
    )


def _check_cast_success(cur: Cursor) -> CheckResult:
    """数値カラムの明示 CAST 成功率を報告（Pitfall 1）。

    ``CAST(kyori AS integer)`` の成功/失敗を件数で報告。失敗は ``WHEN ... IS NOT NULL``
    で回避し、例外ではなく件数で集計する（ゲート自体は fail させない・INFO）。
    """
    columns: dict[str, dict[str, float | int]] = {}

    targets = (
        ("n_race", CAST_COLUMNS_N_RACE),
        ("n_uma_race", CAST_COLUMNS_N_UMA_RACE),
    )
    for table, cols in targets:
        if not cols:
            continue
        cur.execute(f"SELECT count(*) FROM {table} WHERE {JRA_ONLY_FILTER}")
        total = int(cur.fetchone()[0])
        for c in cols:
            try:
                # Pitfall 1: 全 varchar なので数値カラムは明示キャスト相当の検査が必要。
                # ``CAST({c} AS integer)`` は非数値で例外を投げ transaction を abort する
                # ため、事前正規表現でキャスト失敗行を安全に件数集計する（例外安全版）。
                # CR-02: real 列（futan 等・小数）は小数を許容するパターンを使う。整数専用
                # ``'^[0-9]+$'`` では "57.5" を誤って失敗扱いにし cast 成功率を破損していた。
                pattern = r"^[0-9]+(\.[0-9]+)?$" if c in REAL_CAST_COLUMNS else r"^[0-9]+$"
                cur.execute(
                    f"""
                    SELECT count(*) FROM {table}
                    WHERE {JRA_ONLY_FILTER}
                      AND {c} IS NOT NULL
                      AND {c} !~ %s
                    """,
                    (pattern,),
                )
                non_numeric = int(cur.fetchone()[0])
                success = total - non_numeric
                success_pct = (success / total * 100.0) if total else 0.0
                columns[f"{table}.{c}"] = {
                    "total": total,
                    "cast_success": success,
                    "cast_fail": non_numeric,
                    "cast_success_pct": round(success_pct, 4),
                }
            except Exception as exc:  # noqa: BLE001
                columns[f"{table}.{c}"] = {"error": str(exc)}  # type: ignore[assignment]

    return CheckResult(
        name="cast_success",
        passed=True,
        severity="info",
        detail={"columns": columns},
    )


def _check_mojibake(cur: Cursor) -> CheckResult:
    """主要 varchar カラムの mojibake（U+FFFD 含む行）を検出して件数を報告。

    **REVIEWS HIGH #7 必須チェック。** PostgreSQL の Unicode escape 文字列定数
    ``U&'\\+00FFFD'`` で U+FFFD を表現し、``position(...) > 0`` で出現を検知する。

    対象カラムは実DBで存在するものに限定（``kisyu``/``torikishi`` は n_uma_race に
    存在しないため ``kisyuryakusyo``/``chokyosiryakusyo`` に置換・Rule 3）。
    """
    columns: dict[str, dict[str, int]] = {}

    def _scan(table: str, col: str) -> None:
        try:
            cur.execute(
                f"""
                SELECT count(*) FROM {table}
                WHERE {JRA_ONLY_FILTER}
                  AND position({U_FFFD_PG} UESCAPE '\\' IN coalesce({col}, '')) > 0
                """
            )
            cnt = int(cur.fetchone()[0])
            columns[f"{table}.{col}"] = {"count": cnt}
        except Exception as exc:  # noqa: BLE001
            columns[f"{table}.{col}"] = {"error": str(exc)}  # type: ignore[assignment]

    for col in MOJIBAKE_COLUMNS_N_RACE:
        _scan("n_race", col)
    for col in MOJIBAKE_COLUMNS_N_UMA_RACE:
        _scan("n_uma_race", col)

    total_mojibake = sum(
        v.get("count", 0) for v in columns.values() if isinstance(v.get("count"), int)
    )
    return CheckResult(
        name="mojibake",
        passed=True,
        severity="info",
        detail={
            "columns": columns,
            "total_mojibake_rows": total_mojibake,
            "marker": "U+FFFD (REPLACEMENT CHARACTER)",
        },
    )


def _check_code_value_anomalies(cur: Cursor, allowed_codes: dict[str, set[str]]) -> CheckResult:
    """コードカラムが allowed-code-set 外の値を含む件数と割合を報告。

    **REVIEWS HIGH #7 必須チェック。** ``jyokencd5`` / ``gradecd`` / ``jyocd`` /
    ``syubetucd`` の各カラムについて、``NOT IN`` を ``ANY(%s::text[])`` 形式で
    安全に組み立てる（SQL injection 回避・psycopg3 パラメータ埋め込み）。

    これにより ``gradecd='Z'`` や ``jyocd='99'`` 等の不正値が検出される。
    """
    columns: dict[str, dict[str, float | int | str]] = {}

    # 全体件数（割合計算用）
    cur.execute(f"SELECT count(*) FROM n_race WHERE {JRA_ONLY_FILTER}")
    total_jra = int(cur.fetchone()[0])

    # 各コードカラムの検査。jyocd は WHERE 句で BETWEEN '01' AND '10' が既に
    # 入っているため、allowed_codes["jyocd"] 外の値は件数 0 になるはずだが、
    # 検知能力の検証のために全カラムについて同じロジックを走らせる。
    code_columns = ("jyokencd5", "gradecd", "syubetucd")
    for col in code_columns:
        allowed = sorted(allowed_codes.get(col, set()))
        if not allowed:
            columns[col] = {"error": f"allowed-code-set empty for {col}"}
            continue
        try:
            cur.execute(
                f"""
                SELECT count(*) FROM n_race
                WHERE {JRA_ONLY_FILTER}
                  AND {col} IS NOT NULL
                  AND NOT ({col} = ANY(%s::text[]))
                """,
                (allowed,),
            )
            anom = int(cur.fetchone()[0])
            pct = (anom / total_jra * 100.0) if total_jra else 0.0
            columns[col] = {
                "count": anom,
                "pct": round(pct, 4),
                "allowed_count": len(allowed),
            }
        except Exception as exc:  # noqa: BLE001
            columns[col] = {"error": str(exc)}  # type: ignore[assignment]

    # jyocd は JRA フィルタと直接絡むため、全体（JRA 絞り込み無し）で確認
    allowed_jyocd = sorted(allowed_codes.get("jyocd", set()))
    if allowed_jyocd:
        try:
            cur.execute(
                """
                SELECT count(*) FROM n_race
                WHERE jyocd IS NOT NULL
                  AND NOT (jyocd = ANY(%s::text[]))
                """,
                (allowed_jyocd,),
            )
            non_jra_jyocd = int(cur.fetchone()[0])
            columns["jyocd_non_jra"] = {
                "count": non_jra_jyocd,
                "note": "jyocd outside 01-10 (NAR/海外含む)",
                "allowed_count": len(allowed_jyocd),
            }
        except Exception as exc:  # noqa: BLE001
            columns["jyocd_non_jra"] = {"error": str(exc)}  # type: ignore[assignment]

    return CheckResult(
        name="code_value_anomalies",
        passed=True,
        severity="info",
        detail={"columns": columns, "total_jra_rows": total_jra},
    )


# ---------------------------------------------------------------------------
# run_quality_gate: 統合エントリポイント
# ---------------------------------------------------------------------------


def run_quality_gate(cur: Cursor) -> dict[str, Any]:
    """全 BLOCK/INFO チェックを実行し、verdict を含む dict を返す。

    Args:
        cur: psycopg3 cursor（plan 01 の readonly_cur fixture を想定・
            public.n_* への SELECT 権限を持つ raw 読取ロール）

    Returns:
        ``{"verdict": "pass"|"fail", "checks": [...], "degraded_checks_count": int}``

    verdict は severity="block" なチェックが全て passed の場合のみ "pass"。
    それ以外は "fail"。INFO チェックの passed は verdict に影響しない（D-01）。

    **WR-05 degraded visibility:**
    各 INFO check は ``except Exception as exc: ...detail={"error": str(exc)}``
    で query error を dict に格納して継続する。これにより raw 側の column rename 等
    で query が壊れても verdict は pass のまま silent-degradation するリスクがある。
    本関数は ``degraded_checks_count``（``"error"`` キーを含む INFO check 件数）を
    返り値に含め、downstream（``run_quality_report.py`` 等）で閾値監視できるようにする。
    将来的な BLOCK escalation は product decision として保留（本件では単純に可視化のみ）。

    セキュリティ（T-02-02）: 各 check dict は ``name/passed/severity/detail`` のみを
    含む。DSN/password 等の認証情報は一切含めない。
    """
    # allowed-code-set を事前構築（失敗時は例外で fail に傾く・T-02-01）
    allowed_codes = _load_allowed_codes()

    results: list[CheckResult] = []

    # --- BLOCK: 主要5系統テーブル存在 ---
    for t in TARGET_TABLES:
        results.append(_check_table_exists(cur, t))

    # --- BLOCK: JRA 2015 以降データ存在 ---
    results.append(_check_jra_since_2015(cur))

    # --- BLOCK: PK / 自然キー一意 ---
    results.append(_check_n_race_pk_unique(cur))
    results.append(_check_n_uma_race_natural_key_unique(cur))

    # --- INFO: 量的異常レポート ---
    results.append(_check_table_counts(cur))
    results.append(_check_date_range(cur))
    results.append(_check_null_rates(cur))
    results.append(_check_cast_success(cur))

    # --- INFO: HIGH #7 追加 ---
    results.append(_check_mojibake(cur))
    results.append(_check_code_value_anomalies(cur, allowed_codes))

    verdict = "pass" if all(r.passed for r in results if r.severity == "block") else "fail"

    # WR-05: INFO check の silent degradation を可視化。
    # 各 INFO check は ``except Exception`` で ``detail = {"error": str(exc)}`` を格納
    # して継続するため、query 破損等が起きても verdict は pass のまま黙る。downstream
    # で監視できるよう ``degraded_checks_count`` を返り値に含める。
    #
    # INFO check の ``detail`` 構造は2系統ある:
    #   - top-level error: ``detail = {"error": str(exc)}``（例: _check_date_range）
    #   - nested per-column error: ``detail = {"columns": {key: {"error": str(exc)}}}``
    #     （例: _check_cast_success / _check_null_rates / _check_mojibake /
    #      _check_code_value_anomalies）
    # 両方を走査して ``"error"`` キーを含む INFO check を数える。
    def _has_error(detail: Any) -> bool:
        if not isinstance(detail, dict):
            return False
        if "error" in detail:
            return True
        for v in detail.values():
            if isinstance(v, dict) and "error" in v:
                return True
            # 2階層目（``columns`` 配下の per-column dict）も走査
            if isinstance(v, dict):
                for inner in v.values():
                    if isinstance(inner, dict) and "error" in inner:
                        return True
        return False

    degraded_checks_count = sum(1 for r in results if r.severity == "info" and _has_error(r.detail))

    return {
        "verdict": verdict,
        "checks": [asdict(r) for r in results],
        "degraded_checks_count": degraded_checks_count,
    }


__all__ = [
    "CheckResult",
    "run_quality_gate",
    "_load_allowed_codes",
    "_check_table_exists",
    "_check_jra_since_2015",
    "_check_n_race_pk_unique",
    "_check_n_uma_race_natural_key_unique",
    "_check_mojibake",
    "_check_code_value_anomalies",
    "JRA_ONLY_FILTER",
    "TARGET_TABLES",
]
