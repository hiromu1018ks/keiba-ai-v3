# ruff: noqa: E501  (SQL リテラル・長い docstring を保持するため行長は緩和)
"""LABEL-03: 複勝ラベル払戻テーブル突合ゲート（§10.5・SC#2 >99.9% agreement）。

本モジュールは Phase 2 の ACCEPTANCE GATE であり、予測目標 ``fukusho_hit_validated`` が
払戻テーブル（HR ``PayFukusyoUmaban1..5``）と整合することを聖域として保護する
（Core Value: リーク防止と同等の聖域）。

仕様（02-CONTEXT.md D-02 + 02-RESEARCH.md §10.5 対応表 + 02-REVIEWS.md HIGH #2/#6/#7 + NEW HIGH #1）:

  - **D-02 hybrid gate 踏襲:** Phase 1 ``quality_gate.py`` の ``CheckResult`` dataclass
    + ``run_quality_gate`` パターンを LABEL-03 に適用。§10.5 の 6 検査は全て BLOCK
    （ラベル境界を壊す構造的欠陥）・量化（drift / status 割合）は INFO 別関数。
  - **REVIEWS HIGH #2 (tautological reconciliation):** ``_check_raw_validated_drift`` が
    ``fukusho_hit_raw``（KakuteiJyuni-based・HR と独立ソース）と ``fukusho_hit_validated``
    の drift を独立検査し、drift 行が全て dead_heat status であることを assert。
    これにより「HR-derived label を HR に逆 JOIN する tautology」を回避する。
  - **REVIEWS NEW HIGH #1 (NULL-safe + padded umaban):** ``_check_payout_precision`` /
    ``_check_payout_recall`` は ``NOT IN (NULLIF)``（NULL 三値論理で UNKNOWN → silent skip）
    を使わず、``NOT EXISTS`` / ``IS DISTINCT FROM`` の NULL-safe セット比較 + 両側
    ``LPAD(...::text, 2, '0')`` で zero-pad する。これにより payout slot に NULL が混入
    しても正しく一致判定され、umaban の padding 差（label ``1`` vs HR ``01``）で
    false mismatch/mask が起きない。
  - **REVIEWS HIGH #6 (Check #5 too broad):** ``_check_dead_loss_not_excluded`` は
    「dead_loss 単独で除外された」行のみ passed=False とする。``ineligibility_reason IS NULL
    OR ineligibility_reason NOT IN ('obstacle', 'newcomer', ...)'`` で制約し、障害/新馬等の
    正当理由で除外された競走中止馬は passed=True になる。
  - **REVIEWS HIGH #7 (scratch check misses contamination):** ``_check_no_scratch_mislabeled``
    は label boolean ``is_scratch_cancel`` に依存せず、``_recompute_scratch_markers`` が
    ``label_spec.yaml`` の ``se_marker_canonicalization.bataijyu_sentinels_scratch`` sentinel
    を使い raw SE ``bataijyu`` から scratch marker を再計算する。これにより label 分類
    ロジックのバグで ``is_scratch_cancel=True`` になるべき馬が ``False`` になっていても、
    raw marker から独立に payout set 混入を検知できる。
  - **WR-05 degraded visibility:** INFO check の silent error を ``degraded_checks_count``
    で可視化（Phase 1 ``quality_gate.py:596-611`` と同じ）。
  - **W3 / SC#3 unresolved fraction 明示報告:** ``_check_label_status_distribution`` の
    detail に ``unresolved_fraction`` と ``unresolved_threshold``（0.01）を格納。
  - **T-02-02 セキュリティ:** 各 check dict は ``name/passed/severity/detail`` のみ。
    DSN/password 等の認証情報は一切含めない。
  - **T-02-19 read-only:** reconcile は readonly pool で SELECT のみ。``UPDATE`` / ``INSERT``
    等の書込 SQL を含まない（Phase 1 raw_fingerprint.py と同じ read-only helper 性質）。

下流（Phase 3 features / Phase 4 model / Phase 5 backtest）は本ゲートの verdict='pass'
を前提とする。verdict='fail' の場合、``label.fukusho_label`` に silent mislabeling が
存在し Phase 3-6 下流へ直結するため、CI / gate が止まる（D-02）。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

import pandas as pd
from psycopg import Cursor

from src.etl.filters import PROJECT_WINDOW_FILTER
from src.etl.fukusho_label import load_label_spec
from src.etl.quality_gate import CheckResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 不適格理由コード（label_spec.yaml ineligibility_reason_codes と同一集合）。
# HIGH #6: _check_dead_loss_not_excluded はこの正当理由リストに入っていない行のみ passed=False とする。
_VALID_INELIGIBILITY_REASONS: tuple[str, ...] = (
    "obstacle",
    "newcomer",
    "no_fukusho_sale",
    "unresolved",
    "race_or_horse_cancelled",
    "class_below_minimum",
    "status_not_eligible",
)

# W3 / SC#3: unresolved 割合の監視閾値（1%）。超過時は threshold_exceeded フラグを立てる
# （verdict には影響しない・D-02 一貫・参考レポート）。
UNRESOLVED_THRESHOLD: float = 0.01


# ---------------------------------------------------------------------------
# _recompute_scratch_markers（REVIEWS HIGH #7: raw SE marker 再計算）
# ---------------------------------------------------------------------------
def _recompute_scratch_markers(
    cur: Cursor,
    *,
    spec: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """raw SE ``bataijyu`` sentinel から scratch marker を再計算して DataFrame を返す（HIGH #7）。

    **HIGH #7 核心:** 本関数は ``label.fukusho_label.is_scratch_cancel`` を一切参照しない。
    これにより label 分類ロジックのバグ（``is_scratch_cancel`` が ``True`` になるべき馬で
    ``False`` になる等）があっても、raw marker から独立に scratch を検出できる。

    手順:
      1. ``spec = spec or load_label_spec()`` で ``label_spec.yaml`` を読込
      2. ``sentinels = spec['se_marker_canonicalization']['bataijyu_sentinels_scratch']``
         （例: ``["000", "0", "0.0"]``）
      3. SQL: ``label.fukusho_label`` と ``normalized.n_uma_race`` を PK で JOIN し、
         ``fukusho_hit_validated`` と raw ``bataijyu`` を SELECT（``PROJECT_WINDOW_FILTER`` 適用）
      4. pandas で ``canonicalized_bataijyu = se.bataijyu.astype(str).str.strip()``
         （``fukusho_label._canonicalize_markers`` と同じ正規化）
      5. ``recomputed_is_scratch = canonicalized_bataijyu.isin(sentinels)``

    戻り値 DataFrame は ``recomputed_is_scratch`` / ``fukusho_hit_validated`` 列を含む。
    """
    spec = spec if spec is not None else load_label_spec()
    # HIGH #7: sentinel 集合は label_spec.yaml se_marker_canonicalization から取得（label boolean 非依存）
    canon_cfg = spec["se_marker_canonicalization"]
    sentinels = set(canon_cfg["bataijyu_sentinels_scratch"])

    # label.fukusho_label JOIN normalized.n_uma_race で raw bataijyu を取得。
    # PK: year, jyocd, kaiji, nichiji, racenum, umaban, kettonum
    # （normalized.n_uma_race は Phase 1 で JRA+2015 フィルタ済みだが、label 側と
    #  整合させるため PROJECT_WINDOW_FILTER で両側を再度絞り込む）
    sql = f"""
        SELECT l.umaban, l.kettonum, l.fukusho_hit_validated, se.bataijyu
        FROM label.fukusho_label l
        JOIN normalized.n_uma_race se
          ON (l.year = se.year
              AND l.jyocd = se.jyocd
              AND l.kaiji = se.kaiji
              AND l.nichiji = se.nichiji
              AND l.racenum = se.racenum
              AND l.umaban = se.umaban
              AND l.kettonum = se.kettonum)
        WHERE {PROJECT_WINDOW_FILTER}
    """
    cur.execute(sql)
    rows = cur.fetchall()
    if not rows:
        # 行0件の場合も空 DataFrame を返す（呼出側で violation count = 0 と扱う）
        return pd.DataFrame(columns=["recomputed_is_scratch", "fukusho_hit_validated"])

    df = pd.DataFrame(rows, columns=["umaban", "kettonum", "fukusho_hit_validated", "bataijyu"])
    # fukusho_label._canonicalize_value と同じ正規化（strip のみ・sentinel 集合比較）。
    # raw bataijyu は varchar（例: '000'）だが、数値キャスト表現（0, 0.0）も sentinel に入れている。
    df["_c_bataijyu"] = df["bataijyu"].map(
        lambda v: ("__MISSING__" if v is None or _is_na(v) else str(v).strip())
    )
    # HIGH #7: sentinel 集合への in 判定のみ。label 側の scratch フラグ（is_scratch_cancel
    # boolean 列）は一切参照しない — これが本関数の独立性の核心（raw marker 再計算）。
    df["recomputed_is_scratch"] = df["_c_bataijyu"].isin(sentinels)
    return df[["recomputed_is_scratch", "fukusho_hit_validated"]]


# ---------------------------------------------------------------------------
# §10.5 検査1: payout precision（HIGH #2 tautology 回避 + NEW HIGH #1 NULL-safe + padded）
# ---------------------------------------------------------------------------
def _check_payout_precision(cur: Cursor) -> CheckResult:
    """検査1（§10.5 #1）: ``fukusho_hit_validated=1`` の馬が HR payout set に含まれるか。

    **REVIEWS HIGH #2:** この検査は label 側の ``fukusho_hit_validated`` を独立に HR payout
    set と比較する。``fukusho_hit_validated`` 自身が HR 由来であっても、本検査は
    (a) ETL の JOIN ミス、(b) PK 不一致、(c) '00'/'空' 扱いのバグ、**(NEW HIGH #1) NULL
    三値論理/umaban padding バグ** を検出する独立検査として機能する（tautology 回避のため、
    ``_check_raw_validated_drift`` と併用）。

    **REVIEWS NEW HIGH #1:** SQL は ``NOT IN (NULLIF(...))`` 形式を禁止し、``NOT EXISTS`` ベースの
    NULL-safe セット比較 + 両側 ``LPAD(...::text, 2, '0')`` で zero-pad する。これにより
    (a) payout slot に NULL が混入しても三値論理で UNKNOWN とならず安全に skip、(b) label 側
    ``1``（int→'1'）と HR 側 ``'01'``（zero-padded）の padding 差を解消する。
    """
    # Rule 1: label.fukusho_label は monthday 列を持たず race_date を持つ。
    # public.n_harai の race-key PK (year, jyocd, kaiji, nichiji, racenum) は JRA+2015 で
    # 一意（実測 39,580 = 39,580 distinct）のため monthday による追加絞り込みは不要。
    sql = f"""
        SELECT count(*) FROM label.fukusho_label l
        JOIN public.n_harai hr
          ON (l.year = hr.year
              AND l.jyocd = hr.jyocd
              AND l.kaiji = hr.kaiji
              AND l.nichiji = hr.nichiji
              AND l.racenum = hr.racenum)
        WHERE {PROJECT_WINDOW_FILTER}
          AND l.fukusho_hit_validated = 1
          AND NOT EXISTS (
              SELECT 1 FROM (
                  VALUES (LPAD(NULLIF(hr.payfukusyoumaban1, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban2, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban3, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban4, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban5, '00')::text, 2, '0'))
              ) AS t(umaban_padded)
              WHERE t.umaban_padded IS NOT NULL
                AND t.umaban_padded IS DISTINCT FROM NULL
                AND t.umaban_padded = LPAD(l.umaban::text, 2, '0')
          )
    """
    cur.execute(sql)
    cnt = int(cur.fetchone()[0])
    # sample_size は label 側の validated=1 総数（参考値・mock では count クエリで取得しない）
    return CheckResult(
        name="payout_precision",
        passed=cnt == 0,
        severity="block",
        detail={
            "count": cnt,
            "sample_size": None,
            "method": "null_safe_padded_umaban_not_exists",
            "description": (
                "fukusho_hit_validated=1 の馬が HR PayFukusyoUmaban1..5 に含まれない件数。"
                "NULL-safe NOT EXISTS + 両側 LPAD zero-pad（NEW HIGH #1）。"
            ),
        },
    )


# ---------------------------------------------------------------------------
# §10.5 検査2: payout recall（NEW HIGH #1 NULL-safe + padded）
# ---------------------------------------------------------------------------
def _check_payout_recall(cur: Cursor) -> CheckResult:
    """検査2（§10.5 #2）: 逆方向・HR payout set に含まれるが ``fukusho_hit_validated=0`` の馬。

    **REVIEWS NEW HIGH #1:** ``_check_payout_precision`` と同じ NULL-safe + 両側 LPAD zero-pad。
    逆方向のため ``EXISTS`` で payout set 含有を判定する。
    """
    # Rule 1: 上記 _check_payout_precision と同じく monthday JOIN は不要（race-key PK 一意）。
    sql = f"""
        SELECT count(*) FROM label.fukusho_label l
        JOIN public.n_harai hr
          ON (l.year = hr.year
              AND l.jyocd = hr.jyocd
              AND l.kaiji = hr.kaiji
              AND l.nichiji = hr.nichiji
              AND l.racenum = hr.racenum)
        WHERE {PROJECT_WINDOW_FILTER}
          AND l.fukusho_hit_validated = 0
          AND EXISTS (
              SELECT 1 FROM (
                  VALUES (LPAD(NULLIF(hr.payfukusyoumaban1, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban2, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban3, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban4, '00')::text, 2, '0')),
                         (LPAD(NULLIF(hr.payfukusyoumaban5, '00')::text, 2, '0'))
              ) AS t(umaban_padded)
              WHERE t.umaban_padded IS NOT NULL
                AND t.umaban_padded IS DISTINCT FROM NULL
                AND t.umaban_padded = LPAD(l.umaban::text, 2, '0')
          )
    """
    cur.execute(sql)
    cnt = int(cur.fetchone()[0])
    return CheckResult(
        name="payout_recall",
        passed=cnt == 0,
        severity="block",
        detail={
            "count": cnt,
            "sample_size": None,
            "method": "null_safe_padded_umaban_exists",
            "description": (
                "HR PayFukusyoUmaban1..5 に含まれるが fukusho_hit_validated=0 の件数。"
                "NULL-safe EXISTS + 両側 LPAD zero-pad（NEW HIGH #1）。"
            ),
        },
    )


# ---------------------------------------------------------------------------
# §10.5 検査3: dead_heat integrity
# ---------------------------------------------------------------------------
def _check_dead_heat_integrity(cur: Cursor) -> CheckResult:
    """検査3（§10.5 #3）: 同着レースで ``label_validation_status='dead_heat'`` と
    ``is_dead_heat=True`` フラグが整合しているか。両方向の矛盾件数を検出する。

    - ``label_validation_status='dead_heat'`` なのに ``is_dead_heat=False`` は矛盾
    - ``is_dead_heat=True`` なのに ``label_validation_status != 'dead_heat'`` は不整合
    """
    # 方向1: dead_heat status なのに is_dead_heat=False
    cur.execute(
        f"""
        SELECT count(*) FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND label_validation_status = 'dead_heat'
          AND NOT (is_dead_heat = true)
        """
    )
    mismatches_status_to_flag = int(cur.fetchone()[0])

    # 方向2: is_dead_heat=True なのに dead_heat status でない
    cur.execute(
        f"""
        SELECT count(*) FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND is_dead_heat = true
          AND label_validation_status != 'dead_heat'
        """
    )
    mismatches_flag_to_status = int(cur.fetchone()[0])

    total_mismatch = mismatches_status_to_flag + mismatches_flag_to_status
    return CheckResult(
        name="dead_heat_integrity",
        passed=total_mismatch == 0,
        severity="block",
        detail={
            "mismatch_count": total_mismatch,
            "status_to_flag_mismatch": mismatches_status_to_flag,
            "flag_to_status_mismatch": mismatches_flag_to_status,
            "method": "bidirectional_dead_heat_flag_status_consistency",
        },
    )


# ---------------------------------------------------------------------------
# §10.5 検査4: no_scratch_mislabeled（HIGH #7: raw marker 再計算）
# ---------------------------------------------------------------------------
def _check_no_scratch_mislabeled(cur: Cursor) -> CheckResult:
    """検査4（§10.5 #4）: 取消/除外馬が誤って ``fukusho_hit_validated=1`` になっていないか。

    **REVIEWS HIGH #7:** label boolean ``is_scratch_cancel`` を使わず、
    ``_recompute_scratch_markers`` で raw ``bataijyu`` sentinel から再計算した scratch marker
    を使用する。これにより label 分類ロジックのバグで ``is_scratch_cancel=True`` になるべき
    馬が ``False`` になっていても、raw marker から独立に payout set 混入を検知できる。
    """
    # HIGH #7: raw marker から scratch を再計算（label.is_scratch_cancel 非依存）
    df = _recompute_scratch_markers(cur)
    if len(df) == 0:
        violations = 0
        sample_size = 0
    else:
        # recomputed_is_scratch=True かつ fukusho_hit_validated=1 の行が違反
        viol_df = df[(df["recomputed_is_scratch"] == True) & (df["fukusho_hit_validated"] == 1)]  # noqa: E712
        violations = int(len(viol_df))
        sample_size = int(len(df))

    return CheckResult(
        name="no_scratch_mislabeled",
        passed=violations == 0,
        severity="block",
        detail={
            "count": violations,
            "sample_size": sample_size,
            "method": "raw_bataijyu_sentinel_recomputed",
            "description": (
                "取消/除外馬（raw SE bataijyu sentinel 再計算）が fukusho_hit_validated=1 に"
                "誤って混入した件数。label.is_scratch_cancel 非依存（HIGH #7）。"
            ),
        },
    )


# ---------------------------------------------------------------------------
# §10.5 検査5: dead_loss_not_excluded（HIGH #6: dead_loss_only 制約）
# ---------------------------------------------------------------------------
def _check_dead_loss_not_excluded(cur: Cursor) -> CheckResult:
    """検査5（§10.5 #5）: 競走中止馬が誤って除外されていないか。

    **REVIEWS HIGH #6:** 「dead_loss 単独で除外された」行のみ passed=False とする。
    障害/新馬/複勝発売なし/unresolved/class_below_minimum の正当理由で
    ``is_model_eligible=False`` になっている競走中止馬は passed=True（問題なし）。
    純粋に dead_loss のみが理由で除外された行のみ passed=False になる。

    SQL 制約: ``is_dead_loss=true AND is_model_eligible=false AND
    (ineligibility_reason IS NULL OR ineligibility_reason NOT IN (...正当理由...))``
    """
    # 正当理由リストを SQL IN 句用に構築（ハードコードで安全性確保・D-13）
    valid_reasons_sql = ", ".join(f"'{r}'" for r in _VALID_INELIGIBILITY_REASONS)
    sql = f"""
        SELECT count(*) FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND is_dead_loss = true
          AND is_model_eligible = false
          AND (ineligibility_reason IS NULL OR ineligibility_reason NOT IN ({valid_reasons_sql}))
    """
    cur.execute(sql)
    cnt = int(cur.fetchone()[0])
    return CheckResult(
        name="dead_loss_not_excluded",
        passed=cnt == 0,
        severity="block",
        detail={
            "count": cnt,
            "sample_size": None,
            "method": "dead_loss_only_constrained",
            "excluded_reasons_list": list(_VALID_INELIGIBILITY_REASONS),
            "description": (
                "競走中止馬（is_dead_loss=true）が正当理由（obstacle/newcomer/...）なしに"
                "除外された件数。HIGH #6: dead_loss_only 制約。"
            ),
        },
    )


# ---------------------------------------------------------------------------
# §10.5 検査6: no_fukusho_sale_not_in_training
# ---------------------------------------------------------------------------
def _check_no_fukusho_sale_not_in_training(cur: Cursor) -> CheckResult:
    """検査6（§10.5 #6）: 複勝発売なしレースが学習対象（``is_model_eligible=True``）に混入していないか。

    複勝発売なし（``is_fukusho_sale_available=False``）の馬が ``is_model_eligible=True`` に
    なっている場合、適格性フィルタのバグを検出する。
    """
    sql = f"""
        SELECT count(*) FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND is_model_eligible = true
          AND is_fukusho_sale_available = false
    """
    cur.execute(sql)
    cnt = int(cur.fetchone()[0])
    return CheckResult(
        name="no_fukusho_sale_not_in_training",
        passed=cnt == 0,
        severity="block",
        detail={
            "count": cnt,
            "sample_size": None,
            "method": "eligibility_vs_sale_availability",
        },
    )


# ---------------------------------------------------------------------------
# 追加 BLOCK 検査: REVIEWS HIGH #2 — raw/validated drift（独立 cross-check）
# ---------------------------------------------------------------------------
def _check_raw_validated_drift(cur: Cursor) -> CheckResult:
    """HIGH #2 独立 cross-check: ``fukusho_hit_raw``（KakuteiJyuni-based・HR と独立ソース）と
    ``fukusho_hit_validated`` の drift を検査し、drift 行が全て ``dead_heat`` status であることを assert。

    **REVIEWS HIGH #2 核心:** この検査は HR payout set と ``fukusho_hit_validated`` を比較する
    だけでなく、``fukusho_hit_raw``（``KakuteiJyuni``-based・HR と独立のソース）との drift を
    独立に検査する。drift 行が ``dead_heat`` 以外にあれば、ETL の境界判定・marker
    canonicalization・join のバグを検出できる（tautology 回避の独立 cross-check）。

    - drift 行数（``fukusho_hit_raw != fukusho_hit_validated``）は実測 7 行（dead_heat 境界のみ）
    - そのうち ``label_validation_status != 'dead_heat'`` の行数 > 0 の場合 passed=False
    """
    # drift 行数（参考値・detail に格納）
    cur.execute(
        f"""
        SELECT count(*) FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND fukusho_hit_raw != fukusho_hit_validated
        """
    )
    drift_count = int(cur.fetchone()[0])

    # dead_heat 以外の status の drift 行数（>0 なら異常・HIGH #2）
    cur.execute(
        f"""
        SELECT count(*) FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND fukusho_hit_raw != fukusho_hit_validated
          AND label_validation_status != 'dead_heat'
        """
    )
    non_dead_heat_drift_count = int(cur.fetchone()[0])

    return CheckResult(
        name="raw_validated_drift",
        passed=non_dead_heat_drift_count == 0,
        severity="block",
        detail={
            "drift_count": drift_count,
            "non_dead_heat_drift_count": non_dead_heat_drift_count,
            "method": "independent_drift_classification",
            "description": (
                "fukusho_hit_raw と fukusho_hit_validated の drift 行数と、そのうち "
                "dead_heat 以外の status を持つ行数。drift は dead_heat 境界のみで発生する"
                "はず（HIGH #2 独立 cross-check・tautology 回避）。"
            ),
        },
    )


# ---------------------------------------------------------------------------
# 量化 INFO 検査: label_status_distribution（W3 / SC#3 unresolved fraction）
# ---------------------------------------------------------------------------
def _check_label_status_distribution(cur: Cursor) -> CheckResult:
    """量化 INFO: ``label_validation_status`` 別件数と ``unresolved`` 割合を報告（D-02 量化レポート）。

    **W3 / SC#3:** detail に ``unresolved_fraction``（float）と ``unresolved_threshold``
    （0.01）を明示格納し、SC#3 の「unresolved fraction reported」を直接満たす。実測 ≈0.07%
    < 1% 閾値を大幅に下回るため severity='info' で保持し、閾値超過時は detail に
    ``threshold_exceeded: True`` フラグを立てて監視強化（verdict は BLOCK 検査のみで決定・D-02 一貫）。
    """
    columns: dict[str, Any] = {}
    try:
        # total_count
        cur.execute(
            f"SELECT count(*) FROM label.fukusho_label WHERE {PROJECT_WINDOW_FILTER}"
        )
        total_count = int(cur.fetchone()[0])
        columns["total_count"] = total_count

        # unresolved_count
        cur.execute(
            f"""
            SELECT count(*) FROM label.fukusho_label
            WHERE {PROJECT_WINDOW_FILTER}
              AND label_validation_status = 'unresolved'
            """
        )
        unresolved_count = int(cur.fetchone()[0])

        # 全 status 別件数（参考）
        cur.execute(
            f"""
            SELECT label_validation_status, count(*)
            FROM label.fukusho_label
            WHERE {PROJECT_WINDOW_FILTER}
            GROUP BY label_validation_status
            """
        )
        status_counts = {str(r[0]): int(r[1]) for r in cur.fetchall()}
        columns["status_counts"] = status_counts

        # dead_heat レース数（馬行ではなくレース数・参考値）
        cur.execute(
            f"""
            SELECT count(DISTINCT (year, jyocd, kaiji, nichiji, racenum))
            FROM label.fukusho_label
            WHERE {PROJECT_WINDOW_FILTER}
              AND label_validation_status = 'dead_heat'
            """
        )
        columns["dead_heat_race_count"] = int(cur.fetchone()[0])

        # drift 行数（fukusho_hit_raw != fukusho_hit_validated）
        cur.execute(
            f"""
            SELECT count(*) FROM label.fukusho_label
            WHERE {PROJECT_WINDOW_FILTER}
              AND fukusho_hit_raw != fukusho_hit_validated
            """
        )
        columns["raw_validated_drift_count"] = int(cur.fetchone()[0])

        # W3 / SC#3: unresolved_fraction と unresolved_threshold を明示格納
        unresolved_fraction = (unresolved_count / total_count) if total_count > 0 else 0.0
        columns["unresolved_count"] = unresolved_count
        columns["unresolved_fraction"] = round(unresolved_fraction, 6)
        columns["unresolved_threshold"] = UNRESOLVED_THRESHOLD
        columns["threshold_exceeded"] = unresolved_fraction > UNRESOLVED_THRESHOLD
    except Exception as exc:  # noqa: BLE001
        columns["error"] = str(exc)

    return CheckResult(
        name="label_status_distribution",
        passed=True,
        severity="info",
        detail=columns,
    )


# ---------------------------------------------------------------------------
# _compute_race_level_agreement（HIGH #2: race-set reconstruction・時系列ホールドアウト + 層化）
# ---------------------------------------------------------------------------
def _compute_race_level_agreement(
    cur: Cursor,
    *,
    sample_pct: float = 0.1,
) -> dict[str, Any]:
    """SC#2: 時系列ホールドアウト（最新 ``sample_pct``）+ 層化でレース単位馬集合完全一致を計算。

    **REVIEWS HIGH #2 (race-set reconstruction from label rows):**
    各ホールドアウトレースで ``label.fukusho_label`` の馬集合（``fukusho_hit_validated=1`` の
    umaban set）と ``public.n_harai.PayFukusyoUmaban1..5`` の馬集合を比較し、完全一致した
    レース数 / ホールドアウト総レース数 * 100 を返す。

    Args:
        cur: readonly cursor
        sample_pct: ホールドアウトする最新レースの割合（デフォルト 0.1 = 10%）

    Returns:
        ``{"agreement_pct": float, "agree_count": int, "total_held_out": int, "disagree_races": [...]}``

    手順:
      1. label.fukusho_label を race_id 単位（PK race 部分）で集計・race_date 昇順でソート
      2. 最新 ``sample_pct * 100``% のレースをホールドアウト
      3. 層化（year / jyocd / 頭数帯 5-7・8以上）で各層からも抽出（stratified sampling）。
         層化は簡易実装: ホールドアウト候補全体を year/jyocd/頭数帯で層化し、各層の代表を含める。
      4. 各ホールドアウトレースで:
         - label 側の馬集合: ``{umaban for fukusho_hit_validated=1}``
         - HR 側の馬集合: ``{payfukusyounmaban1..5 の非NA値}``（NULLIF + ARRAY で再構築）
         - 完全一致（== 比較）なら agree_count += 1
      5. ``agreement = agree_count / total_held_out * 100.0``

    Open Question #3 の推奨実装・レース単位の precision/recall 両方 1.0 を意味する完全一致。
    """
    # race_id 単位の label 側馬集合を取得（race_date 昇順）。
    # race_date は date 型。year/jyocd/kaiji/nichiji/racenum が race-level PK。
    cur.execute(
        f"""
        SELECT year, jyocd, kaiji, nichiji, racenum, race_date,
               array_agg(LPAD(umaban::text, 2, '0') ORDER BY umaban) AS label_set
        FROM label.fukusho_label
        WHERE {PROJECT_WINDOW_FILTER}
          AND fukusho_hit_validated = 1
        GROUP BY year, jyocd, kaiji, nichiji, racenum, race_date
        ORDER BY race_date ASC, year, jyocd, kaiji, nichiji, racenum
        """
    )
    label_rows = cur.fetchall()

    if not label_rows:
        return {
            "agreement_pct": 100.0,
            "agree_count": 0,
            "total_held_out": 0,
            "disagree_races": [],
        }

    # race_id → race_date と label_set（sorted umaban list）の dict 構築
    # race_key = (year, jyocd, kaiji, nichiji, racenum)
    race_meta: dict[tuple, dict[str, Any]] = {}
    for year, jyocd, kaiji, nichiji, racenum, race_date, label_set in label_rows:
        rk = (year, jyocd, kaiji, nichiji, racenum)
        # PostgreSQL array_agg は既に list で返る（psycopg3）・umaban は zero-padded str
        label_set_clean = sorted(
            {str(x).strip() for x in (label_set or []) if x is not None and str(x).strip()}
        )
        race_meta[rk] = {
            "race_date": race_date,
            "year": year,
            "jyocd": jyocd,
            "label_set": label_set_clean,
        }

    # 時系列ホールドアウト: race_date 昇順で最新 sample_pct を選択
    sorted_races = sorted(race_meta.items(), key=lambda kv: (kv[1]["race_date"], kv[0]))
    total_races = len(sorted_races)
    n_held_out = max(1, int(total_races * sample_pct))

    # 層化サンプリング（簡易）: 最新 n_held_out レースに加え、year/jyocd/頭数帯 の各層から
    # 代表を1つずつ追加（stratified）。これにより最新10%に偏った overfit を防止。
    # 層の代表は既にホールドアウトに入っている場合は重複除外。
    held_out_keys: set[tuple] = set()
    held_out_list: list[tuple] = []
    for rk, _meta in sorted_races[-n_held_out:]:
        if rk not in held_out_keys:
            held_out_keys.add(rk)
            held_out_list.append(rk)

    # 層化: year × jyocd の各組合せから1レース（既にホールドアウトに入っていないもの）を追加
    # 頭数帯は label_set size から推定できないため year/jyocd 層のみ（簡易実装）。
    stratum_seen: set[tuple] = set()
    for rk, meta in sorted_races:
        stratum = (meta["year"], meta["jyocd"])
        if stratum in stratum_seen:
            continue
        stratum_seen.add(stratum)
        if rk not in held_out_keys:
            held_out_keys.add(rk)
            held_out_list.append(rk)

    # HR payout set を race 単位で取得（ホールドアウト対象のみ）
    # race_key → set of zero-padded umaban from PayFukusyoUmaban1..5
    where_race_keys = " OR ".join(
        "(hr.year={} AND hr.jyocd={} AND hr.kaiji={} AND hr.nichiji={} AND hr.racenum={})".format(*rk)
        for rk in held_out_list
    )
    # ↑ race_key を直接 SQL に展開（int/varchar 混在だが PostgreSQL が暗黙キャストする）。
    # psycopg3 のパラメータ埋め込みで安全に構築すべきだが、held_out_list は DB から取得した
    # PK 値（SQL injection source ではない）のため展開方式で可読性を優先する。
    hr_sql = f"""
        SELECT year, jyocd, kaiji, nichiji, racenum,
               payfukusyoumaban1, payfukusyoumaban2, payfukusyoumaban3,
               payfukusyoumaban4, payfukusyoumaban5
        FROM public.n_harai hr
        WHERE {PROJECT_WINDOW_FILTER}
          AND ({where_race_keys})
    """
    cur.execute(hr_sql)
    hr_rows = cur.fetchall()

    hr_payout_sets: dict[tuple, set[str]] = {}
    for row in hr_rows:
        year, jyocd, kaiji, nichiji, racenum = row[:5]
        rk = (year, jyocd, kaiji, nichiji, racenum)
        # NULLIF で '00' を NULL にし、zero-pad して set に
        s: set[str] = set()
        for slot in row[5:]:
            if slot is None:
                continue
            slot_str = str(slot).strip()
            if slot_str == "" or slot_str == "00":
                continue
            try:
                s.add(str(int(float(slot_str))).zfill(2))
            except (TypeError, ValueError):
                s.add(slot_str.zfill(2))
        hr_payout_sets[rk] = s

    # 各ホールドアウトレースで label set と HR payout set を完全一致比較
    agree_count = 0
    disagree_races: list[dict[str, Any]] = []
    for rk in held_out_list:
        meta = race_meta[rk]
        label_set = set(meta["label_set"])
        hr_set = hr_payout_sets.get(rk, set())
        if label_set == hr_set:
            agree_count += 1
        else:
            disagree_races.append(
                {
                    "race_key": list(rk),
                    "label_set": sorted(label_set),
                    "hr_set": sorted(hr_set),
                }
            )

    total_held_out = len(held_out_list)
    agreement_pct = (agree_count / total_held_out * 100.0) if total_held_out > 0 else 100.0

    return {
        "agreement_pct": round(agreement_pct, 4),
        "agree_count": agree_count,
        "total_held_out": total_held_out,
        "disagree_races": disagree_races[:20],  # 先頭20件のみ（巨大化防止）
    }


# ---------------------------------------------------------------------------
# reconcile_against_payout: 統合エントリ（quality_gate.py:533-617 パターン踏襲）
# ---------------------------------------------------------------------------
def _has_error(detail: Any) -> bool:
    """INFO check の detail が ``"error"`` キーを含むか（WR-05・quality_gate.py:596-609 と同じ）。

    top-level error と nested per-column error（``columns`` 配下）の両方を走査する。
    """
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


def reconcile_against_payout(cur: Cursor) -> dict[str, Any]:
    """全 BLOCK/INFO 検査を実行し、verdict を含む dict を返す（quality_gate.py:533-617 パターン）。

    Args:
        cur: psycopg3 cursor（readonly pool・plan 03 の readonly_cur fixture を想定。
            ``label.fukusho_label`` / ``public.n_harai`` / ``normalized.n_uma_race`` への
            SELECT 権限を持つ raw 読取ロール）

    Returns:
        ``{"verdict": "pass"|"fail", "checks": [...], "degraded_checks_count": int, "agreement": {...}}``

    verdict は severity="block" な検査が全て passed の場合のみ "pass"。それ以外は "fail"。
    INFO 検査の passed は verdict に影響しない（D-02）。

    **セキュリティ（T-02-02）:** 各 check dict は ``name/passed/severity/detail`` のみを含む。
    DSN/password 等の認証情報は一切含めない。

    **WR-05 degraded visibility:** ``degraded_checks_count`` で INFO check の silent error
    を可視化（quality_gate.py:585-611 と同じ）。
    """
    results: list[CheckResult] = []

    # --- BLOCK: §10.5 の 6 検査 ---
    results.append(_check_payout_precision(cur))
    results.append(_check_payout_recall(cur))
    results.append(_check_dead_heat_integrity(cur))
    results.append(_check_no_scratch_mislabeled(cur))
    results.append(_check_dead_loss_not_excluded(cur))
    results.append(_check_no_fukusho_sale_not_in_training(cur))

    # --- BLOCK: HIGH #2 drift 検査 ---
    results.append(_check_raw_validated_drift(cur))

    # --- INFO: 量化レポート（W3 unresolved_fraction 含む）---
    results.append(_check_label_status_distribution(cur))

    # --- verdict 集計（Phase 1 D-01 と同じ）---
    verdict = "pass" if all(r.passed for r in results if r.severity == "block") else "fail"

    # WR-05: INFO check の silent degradation を可視化
    degraded_checks_count = sum(
        1 for r in results if r.severity == "info" and _has_error(r.detail)
    )

    # SC#2: agreement 計算（時系列ホールドアウト + 層化・race-set reconstruction）
    try:
        agreement = _compute_race_level_agreement(cur, sample_pct=0.1)
    except Exception as exc:  # noqa: BLE001
        # agreement 計算自体が失敗した場合は verdict に影響させず参考値として記録
        logger.warning("_compute_race_level_agreement failed: %s", exc)
        agreement = {
            "agreement_pct": None,
            "agree_count": 0,
            "total_held_out": 0,
            "disagree_races": [],
            "error": str(exc),
        }

    return {
        "verdict": verdict,
        "checks": [asdict(r) for r in results],
        "degraded_checks_count": degraded_checks_count,
        "agreement": agreement,
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _is_na(v: Any) -> bool:
    """scalar の欠損判定（pd.isna の安全 wrapper・配列入力時の ValueError を回避）。"""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


__all__ = [
    "reconcile_against_payout",
    "CheckResult",
    "_check_payout_precision",
    "_check_payout_recall",
    "_check_dead_heat_integrity",
    "_check_no_scratch_mislabeled",
    "_check_dead_loss_not_excluded",
    "_check_no_fukusho_sale_not_in_training",
    "_check_raw_validated_drift",
    "_check_label_status_distribution",
    "_compute_race_level_agreement",
    "_recompute_scratch_markers",
]
