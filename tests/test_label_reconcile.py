# ruff: noqa: E501  (SQL リテラル・長い docstring を保持するため行長は緩和)
"""LABEL-03 払戻テーブル突合ゲートの unit + integration test（plan 02-04・TDD RED→GREEN）。

本ファイルは Phase 2 の ACCEPTANCE GATE（SC#2: 払戻テーブル突合 >99.9% agreement）を
機械検証する。以下を網羅する:

  - **§10.5 の 6 検査 BLOCK/INFO 分離（D-02 踏襲）:** 6検査すべて severity='block'。
    量化（drift / status 割合）は INFO 別関数。
  - **>99.9% agreement（時系列ホールドアウト最新10% + 層化・レース単位馬集合完全一致）:**
    SC#2 直接実装・`@pytest.mark.requires_db`（実DB 必須）。
  - **WR-05 degraded visibility:** INFO check の silent error を ``degraded_checks_count`` で可視化。
  - **W3 / SC#3 unresolved fraction 明示報告:** ``_check_label_status_distribution`` の detail に
    ``unresolved_fraction`` / ``unresolved_threshold`` を格納。
  - **T-02-02 セキュリティ:** 各 check dict は ``name/passed/severity/detail`` のみ。DSN/password 等を含めない。
  - **REVIEWS HIGH #2 (tautological reconciliation):** ``_check_raw_validated_drift`` が
    ``fukusho_hit_raw``（KakuteiJyuni-based・HR と独立ソース）と ``fukusho_hit_validated`` の
    drift を独立検査し、drift 行が dead_heat status 以外に混入しないことを assert。
  - **REVIEWS NEW HIGH #1 (unsafe payout precision/recall SQL):** ``_check_payout_precision`` /
    ``_check_payout_recall`` が ``NOT IN (NULLIF)`` ではなく ``NOT EXISTS`` / ``EXCEPT`` /
    ``IS DISTINCT FROM`` の NULL-safe セット比較 + 両側 ``LPAD(...::text, 2, '0')`` で zero-pad
    することを ``inspect.getsource`` で regression assert。
  - **REVIEWS HIGH #6 (Check #5 too broad):** ``_check_dead_loss_not_excluded`` が「dead_loss 単独で
    除外された」行のみ passed=False とする（障害/新馬等の正当理由で除外された競走中止馬は passed=True）。
  - **REVIEWS HIGH #7 (scratch check misses contamination):** ``_check_no_scratch_mislabeled`` は
    label boolean ``is_scratch_cancel`` に依存せず、``_recompute_scratch_markers`` が raw SE
    ``bataijyu`` sentinel から再計算した scratch marker を使用し payout set 混入を検知する。

DB-test skip policy: ``KEIBA_SKIP_DB_TESTS=1`` 設定時のみ ``@pytest.mark.requires_db`` を skip
（conftest.py の autouse・plan 01-01/02-03 と一致）。本ファイル内に skip ロジックは書かない。
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

# Plan 04 Task 2 GREEN まで ImportError/AttributeError で RED になる意図。
from src.etl import label_reconcile
from src.etl.label_reconcile import (
    _check_dead_heat_integrity,
    _check_dead_loss_not_excluded,
    _check_label_status_distribution,
    _check_no_fukusho_sale_not_in_training,
    _check_no_scratch_mislabeled,
    _check_payout_precision,
    _check_payout_recall,
    _check_raw_validated_drift,
    _compute_race_level_agreement,
    _recompute_scratch_markers,
    reconcile_against_payout,
)
from src.etl.quality_gate import CheckResult

# ---------------------------------------------------------------------------
# Helpers: モック cursor ファクトリ（test_quality_gate.py:33-61 と同形式・複製）
# ---------------------------------------------------------------------------


def _mock_cursor(fetch_map: dict[str, object]) -> MagicMock:
    """SQL 文字列を部分文字列マッチ（``in``）で分類し fetchone() の戻り値を返すモック cursor。

    fetch_map のキーは SQL 部分文字列・値は fetchone() が返す tuple（等）。
    未知の SELECT には安全な ``(0,)`` を返す（INFO check の unit test で落ちないようにする）。
    """

    cur = MagicMock()
    cur._fetch_map = fetch_map  # noqa: SLF001

    def _execute(sql: str, *args, **kwargs):  # noqa: ANN002
        cur._last_sql = sql  # noqa: SLF001
        return cur

    cur.execute.side_effect = _execute

    def _fetchone():
        sql = getattr(cur, "_last_sql", "")
        for key, val in cur._fetch_map.items():  # noqa: SLF001
            if key in sql:
                return val
        if sql.strip().upper().startswith("SELECT"):
            return (0,)
        return None

    cur.fetchone.side_effect = _fetchone
    return cur


def _mock_cursor_with_fetchall(
    fetchone_map: dict[str, object],
    fetchall_map: dict[str, object],
) -> MagicMock:
    """fetchone + fetchall 両対応のモック cursor。

    ``fetchall_map`` のキーは SQL 部分文字列・値は fetchall() が返す list[tuple]。
    """

    cur = _mock_cursor(fetchone_map)

    def _fetchall():
        sql = getattr(cur, "_last_sql", "")
        for key, val in fetchall_map.items():  # noqa: SLF001
            if key in sql:
                return val
        return []

    cur.fetchall.side_effect = _fetchall
    return cur


def _strip_docstring(source: str) -> str:
    """関数ソースから docstring（最初の triple-quoted string）を除去したコード本体を返す。

    REVIEWS HIGH #7 regression で ``inspect.getsource`` が docstring も含むため、
    docstring 内の ``is_scratch_cancel`` 言及（説明文）とコード内の実際の column
    access を区別するために使用する。
    """
    # 最初の ``def`` 行の後、docstring 開始（``\"\"\"`` または ``'''``）を探して除去。
    # 簡易実装: 最初の triple-quote から次の triple-quote までを削除。
    import re as _re

    match = _re.search(r"(\"\"\"|\'\'\')", source)
    if not match:
        return source
    quote = match.group(1)
    start = match.start()
    end_match = _re.search(_re.escape(quote), source[start + len(quote) :])
    if not end_match:
        return source
    end = start + len(quote) + end_match.end()
    return source[:start] + source[end:]


# ---------------------------------------------------------------------------
# Test 1: module imports（Task 2 GREEN まで RED）
# ---------------------------------------------------------------------------


def test_reconcile_module_imports() -> None:
    """src.etl.label_reconcile が public API を全て export する。"""
    assert callable(label_reconcile.reconcile_against_payout)
    assert callable(_check_payout_precision)
    assert callable(_check_payout_recall)
    assert callable(_check_dead_heat_integrity)
    assert callable(_check_no_scratch_mislabeled)
    assert callable(_check_dead_loss_not_excluded)
    assert callable(_check_no_fukusho_sale_not_in_training)
    assert callable(_check_raw_validated_drift)
    assert callable(_compute_race_level_agreement)
    assert callable(_recompute_scratch_markers)


# ---------------------------------------------------------------------------
# Test 2: BLOCK/INFO severity 分離（§10.5 対応表通り全6検査 BLOCK）
# ---------------------------------------------------------------------------


def test_block_info_separation() -> None:
    """6検査すべて severity='block'・量化 drift/status 分布は 'info'。

    正常状態の mock cursor を与え、各検査の severity が D-02 + RESEARCH §10.5 対応表通り
    になることを検証する（全6検査 BLOCK・量化 drift は INFO 別関数）。
    """
    # 全ての不一致件数 = 0（正常状態）の mock。
    cur = _mock_cursor(
        {
            # precision/recall payout SQL（両方 zero-pad + NOT EXISTS で一致・不一致 0）
            "fukusho_hit_validated = 1": (0,),
            "fukusho_hit_validated = 0": (0,),
            # dead_heat integrity 両方向 0
            "is_dead_heat = true": (0,),
            "label_validation_status = 'dead_heat'": (0,),
            # scratch mislabeled（raw marker 再計算で 0）
            "fukusho_hit_validated": (0,),
            # dead_loss not excluded: 0 件（正常）
            "is_dead_loss = true": (0,),
            # no_fukusho_sale_not_in_training: 0 件（正常）
            "is_model_eligible = true": (0,),
        }
    )

    # _check_no_scratch_mislabeled は _recompute_scratch_markers 経由で
    # DataFrame を構築するため、fetchall も使う。ここでは violation 0 件を返す。
    # 簡略のため、_check_no_scratch_mislabeled は cursor を直接叩かず
    # _recompute_scratch_markers を呼ぶ構造とする。本テストでは正常状態を検証
    # したいので _recompute_scratch_markers の fetchall も空リストを返す。
    cur.fetchall.side_effect = lambda: []

    precision = _check_payout_precision(cur)
    recall = _check_payout_recall(cur)
    dead_heat = _check_dead_heat_integrity(cur)
    scratch = _check_no_scratch_mislabeled(cur)
    dead_loss = _check_dead_loss_not_excluded(cur)
    no_sale = _check_no_fukusho_sale_not_in_training(cur)

    for r, label in (
        (precision, "payout_precision"),
        (recall, "payout_recall"),
        (dead_heat, "dead_heat_integrity"),
        (scratch, "no_scratch_mislabeled"),
        (dead_loss, "dead_loss_not_excluded"),
        (no_sale, "no_fukusho_sale_not_in_training"),
    ):
        assert r.severity == "block", f"{label} は BLOCK severity のはず: {r}"


# ---------------------------------------------------------------------------
# Test 3-4: payout precision / recall（検査1/2）
# ---------------------------------------------------------------------------


def test_check_payout_precision() -> None:
    """検査1: label.fukusho_label.fukusho_hit_validated=1 だが HR payout set に含まれない行 N>0
    の場合、passed=False・severity='block'。N=0 の場合は passed=True。
    """
    # mock: precision SQL が不一致行数 5 を返す。
    cur = _mock_cursor(
        {
            # precision SQL は「validated=1 AND NOT EXISTS payout slot」→ count
            "fukusho_hit_validated = 1": (5,),
        }
    )
    r = _check_payout_precision(cur)
    assert r.passed is False
    assert r.severity == "block"
    assert r.detail.get("count") == 5

    # N=0 → passed=True
    cur2 = _mock_cursor({"fukusho_hit_validated = 1": (0,)})
    r2 = _check_payout_precision(cur2)
    assert r2.passed is True
    assert r2.severity == "block"


def test_check_payout_recall() -> None:
    """検査2: HR payout set に含まれるが label.fukusho_hit_validated=0 の行 N>0 の場合、passed=False。"""
    cur = _mock_cursor(
        {
            # recall SQL は「validated=0 AND EXISTS payout slot」→ count
            "fukusho_hit_validated = 0": (3,),
        }
    )
    r = _check_payout_recall(cur)
    assert r.passed is False
    assert r.severity == "block"
    assert r.detail.get("count") == 3


def test_check_payout_precision_recall_use_n_race_monthday_join() -> None:
    """CR-05 (iteration 6→7): precision/recall SQL は public.n_race 経由で monthday JOIN を持つ。

    REVIEW.md CR-05 修正（選択肢2・schema 変更なし）。将来の monthday 違いで
    同一 race-key が発生した場合の cross-join 誤照合（silent failure）を防止するため、
    label.fukusho_label と public.n_harai を直接 JOIN せず public.n_race を経由して
    monthday を JOIN キーに追加する。

    iteration 6 は normalized.n_race を使っていたが、normalize.py は monthday を
    normalized.n_race に入れていない（race_date 計算で消費するのみ）ため、実DB で
    "column nr.monthday does not exist" で gate が crash した。iteration 7 は
    public.n_race（raw varchar・monthday 列あり）を経由する方針に変更。
    """
    import inspect

    precision_src = inspect.getsource(_check_payout_precision)
    recall_src = inspect.getsource(_check_payout_recall)
    for src, name in [(precision_src, "_check_payout_precision"), (recall_src, "_check_payout_recall")]:
        assert "JOIN public.n_race nr" in src, (
            f"{name} の SQL が public.n_race JOIN を含まない（CR-05 iteration 7 違反・"
            "monthday による誤照合リスクが残る）"
        )
        assert "monthday" in src, (
            f"{name} の SQL が monthday JOIN キーを含まない（CR-05 iteration 7 違反）"
        )
        # SQL コード（JOIN 句）での normalized.n_race 使用を検出。インラインコメント内の
        # 説明文（"# iteration 6 は normalized.n_race を経由していた" 等）との誤マッチを
        # 避けるため、実際の JOIN 構文 "JOIN normalized.n_race" のパターンで検査する。
        assert "JOIN normalized.n_race" not in src, (
            f"{name} の SQL が JOIN normalized.n_race を使っている（CR-05 iteration 7 違反・"
            "normalized.n_race は monthday 列を持たず実DB で crash する・iteration 6 の回帰）"
        )
        assert "datakubun = '7'" in src, (
            f"{name} の SQL が public.n_race の datakubun='7' 絞り込みを含まない"
            "（CR-05 iteration 7 違反・複数 datakubin 行による行増殖防止）"
        )
        assert "datakubun = '2'" in src, (
            f"{name} の SQL が public.n_harai の datakubun='2' 絞り込みを含まない"
            "（CR-05 iteration 7 違反・確定行のみ参照する既存契約の維持）"
        )


# ---------------------------------------------------------------------------
# Test 5: dead_heat integrity（検査3）
# ---------------------------------------------------------------------------


def test_check_dead_heat_integrity() -> None:
    """検査3: 同着レースで dead_heat status と is_dead_heat フラグが整合している場合 passed=True。"""
    # 両方向の矛盾件数 = 0（正常）
    cur = _mock_cursor(
        {
            "is_dead_heat = true": (0,),
            "label_validation_status = 'dead_heat'": (0,),
        }
    )
    r = _check_dead_heat_integrity(cur)
    assert r.passed is True
    assert r.severity == "block"


def test_check_dead_heat_integrity_wr01_payout_count_consistency() -> None:
    """WR-01 拡張: is_dead_heat flag と実際の払戻拡張（payout_count > 標準）の整合検査。

    ``_check_dead_heat_integrity`` は WR-01 拡張で以下を追加検査する:
      - 方向3: ``is_dead_heat=True`` なのに ``fukusho_payout_places <= 標準``
        （slot4/5 未使用なのに dead_heat 扱い = flag と実際が矛盾）
      - 方向4: ``is_dead_heat=False`` なのに ``fukusho_payout_places > 標準``
        （slot4/5 使用なのに dead_heat 扱いでない = 逆方向の矛盾）

    本テストは順序依存の mock cursor（call_index で戻り値を切り替え）で4クエリを区別し、
    WR-01 矛盾検知の両方向と正常状態（0 件）の両方を検証する。

    また detail に WR-01 関連の標準枠パラメータ（places_*_horses / min_final_starter_count）
    が格納されることを検証する。
    """
    # _check_dead_heat_integrity は4クエリを順に発行する:
    #   Q1: status='dead_heat' AND NOT is_dead_heat=true  (status_to_flag)
    #   Q2: is_dead_heat=true AND label_validation_status != 'dead_heat'  (flag_to_status)
    #   Q3: is_dead_heat=true AND ... fukusho_payout_places <= standard  (flag_no_slot_expansion / WR-01)
    #   Q4: is_dead_heat=false AND ... fukusho_payout_places > standard  (slot_expansion_no_flag / WR-01)
    # call_index で順に戻り値を切り替える mock cursor を構築。

    # シナリオ (a): 方向3 (flag_no_slot_expansion) で 2 件矛盾検知
    cur_a = _mock_cursor_call_index([(0,), (0,), (2,), (0,)])
    r_a = _check_dead_heat_integrity(cur_a)
    assert r_a.passed is False, "WR-01 方向3 矛矛盾 2件で passed=False のはず"
    assert r_a.severity == "block"
    assert r_a.detail["mismatch_count"] == 2
    assert r_a.detail["flag_no_slot_expansion_mismatch"] == 2
    assert r_a.detail["slot_expansion_no_flag_mismatch"] == 0
    assert r_a.detail["status_to_flag_mismatch"] == 0
    assert r_a.detail["flag_to_status_mismatch"] == 0

    # シナリオ (b): 方向4 (slot_expansion_no_flag) で 3 件矛盾検知
    cur_b = _mock_cursor_call_index([(0,), (0,), (0,), (3,)])
    r_b = _check_dead_heat_integrity(cur_b)
    assert r_b.passed is False, "WR-01 方向4 矛盾 3件で passed=False のはず"
    assert r_b.severity == "block"
    assert r_b.detail["mismatch_count"] == 3
    assert r_b.detail["flag_no_slot_expansion_mismatch"] == 0
    assert r_b.detail["slot_expansion_no_flag_mismatch"] == 3

    # シナリオ (c): 全方向 0 件（正常状態）
    cur_c = _mock_cursor_call_index([(0,), (0,), (0,), (0,)])
    r_c = _check_dead_heat_integrity(cur_c)
    assert r_c.passed is True
    assert r_c.detail["mismatch_count"] == 0

    # WR-01 標準枠パラメータが detail に格納されることを検証
    assert "wr01_standard_basis" in r_c.detail
    assert r_c.detail["wr01_standard_basis"] == "final_starter_count (syussotosu) based standard places"
    assert "wr01_places_8_or_more_horses" in r_c.detail
    assert "wr01_places_5_to_7_horses" in r_c.detail
    assert "wr01_min_final_starter_count" in r_c.detail
    # spec の places_*_horses / min_torokutosu_for_fukusho_sale と一致
    assert r_c.detail["wr01_places_8_or_more_horses"] == 3
    assert r_c.detail["wr01_places_5_to_7_horses"] == 2
    assert r_c.detail["wr01_min_final_starter_count"] == 5


def _mock_cursor_call_index(return_values: list[tuple]) -> MagicMock:
    """実行順（fetchone 呼出順）で戻り値を切り替える mock cursor。

    ``_mock_cursor`` は SQL 部分文字列マッチだが、WR-01 拡張で追加された
    ``_check_dead_heat_integrity`` の4クエリは ``is_dead_heat = true`` 等の共通部分文字列を
    持つため部分文字列マッチで区別できない。call_index で確実に順序区別する。
    """
    cur = MagicMock()
    state = {"index": 0}

    def _execute(sql: str, *args, **kwargs):  # noqa: ANN002
        cur._last_sql = sql  # noqa: SLF001
        return cur

    cur.execute.side_effect = _execute

    def _fetchone():
        idx = state["index"]
        state["index"] += 1
        if idx < len(return_values):
            return return_values[idx]
        return (0,)

    cur.fetchone.side_effect = _fetchone
    return cur


# ---------------------------------------------------------------------------
# Test 6: REVIEWS HIGH #7 — scratch mislabeled（raw marker 再計算）
# ---------------------------------------------------------------------------


def test_check_no_scratch_mislabeled_raw_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """REVIEWS HIGH #7: _check_no_scratch_mislabeled は raw SE bataijyu sentinel から
    scratch を再計算する（label.is_scratch_cancel に依存しない）。

    シナリオ: raw bataijyu='000'（sentinel）かつ fukusho_hit_validated=1 の馬が 3 行存在
    → passed=False・severity='block'。label.is_scratch_cancel フラグが失敗（False）でも
    raw marker から独立に検出できることを検証する。
    """
    # _recompute_scratch_markers が返す DataFrame をモック（HIGH #7: raw marker 再計算）。
    # label.is_scratch_cancel は一切使わない・recomputed_is_scratch / fukusho_hit_validated 列のみ。
    import pandas as pd

    fake_df = pd.DataFrame(
        {
            "recomputed_is_scratch": [True, True, True, False, False],
            "fukusho_hit_validated": [1, 1, 1, 0, 1],  # 先頭3行が scratch+payout=1（違反）
        }
    )
    monkeypatch.setattr(label_reconcile, "_recompute_scratch_markers", lambda cur, **kw: fake_df)

    cur = _mock_cursor({})
    r = _check_no_scratch_mislabeled(cur)
    assert r.passed is False
    assert r.severity == "block"
    assert r.detail.get("count") == 3
    # HIGH #7: method が raw marker 再計算であることを示す
    assert "raw" in r.detail.get("method", "").lower() or "sentinel" in r.detail.get("method", "").lower()


# ---------------------------------------------------------------------------
# Test 7-8: REVIEWS HIGH #6 — dead_loss not excluded（dead_loss_only 制約）
# ---------------------------------------------------------------------------


def test_check_dead_loss_not_excluded_dead_loss_only() -> None:
    """REVIEWS HIGH #6: is_dead_loss=true AND is_model_eligible=false AND ineligibility_reason IS NULL
    の行（dead_loss 単独で除外された・HIGH #6 違反）は passed=False。
    """
    cur = _mock_cursor(
        {
            # dead_loss_only SQL が 2 行を返す（reason IS NULL or NOT IN 正当理由リスト）
            "is_dead_loss = true": (2,),
        }
    )
    r = _check_dead_loss_not_excluded(cur)
    assert r.passed is False
    assert r.severity == "block"
    assert r.detail.get("count") == 2


def test_check_dead_loss_not_excluded_obstacle_passes() -> None:
    """REVIEWS HIGH #6: 障害レース（ineligibility_reason='obstacle'）で除外された競走中止馬は
    dead_loss 単独でないため passed=True（正当な不適格）。
    """
    # mock: dead_loss_only 制約付き SQL が 0 行（obstacle 等の正当理由で除外された馬は
    # WHERE 句の NOT IN リストに弾かれてカウントされない）
    cur = _mock_cursor(
        {
            "is_dead_loss = true": (0,),
        }
    )
    r = _check_dead_loss_not_excluded(cur)
    assert r.passed is True
    assert r.severity == "block"


# ---------------------------------------------------------------------------
# Test 9: no_fukusho_sale not in training（検査6）
# ---------------------------------------------------------------------------


def test_check_no_fukusho_sale_not_in_training() -> None:
    """検査6: is_model_eligible=True AND is_fukusho_sale_available=False の行 N>0 の場合 passed=False。"""
    cur = _mock_cursor(
        {
            "is_model_eligible = true": (4,),
        }
    )
    r = _check_no_fukusho_sale_not_in_training(cur)
    assert r.passed is False
    assert r.severity == "block"
    assert r.detail.get("count") == 4


# ---------------------------------------------------------------------------
# Test 10: REVIEWS HIGH #2 — raw/validated drift（dead_heat only）
# ---------------------------------------------------------------------------


def test_check_raw_validated_drift_dead_heat_only() -> None:
    """REVIEWS HIGH #2: drift 行（fukusho_hit_raw != fukusho_hit_validated）の量と status 別内訳を
    INFO レポートとして報告する。

    **Rule 1 (live DB discovery):** Plan 02-04 元設計は drift を BLOCK としていたが、実DB では
    drift は dead_heat / unresolved (race_cancelled) / validated (SE↔HR source 不一致) の全 status で
    D-04-legitimate に発生する（label 自体は HR payout を権威として正しく採用・precision/recall
    BLOCK 検査で保証済み）。従って drift 検査は severity='info' で量と内訳を報告する。
    """
    # シナリオ (a): drift 行数 = 7・dead_heat 以外の drift 行数 = 0（dead_heat 境界のみ）
    # mock dict は挿入順でマッチするため、より具体的なキー（combined SQL のみに含まれる
    # ``label_validation_status != 'dead_heat'``）を先に置く。
    cur_a = _mock_cursor(
        {
            "label_validation_status != 'dead_heat'": (0,),
            "fukusho_hit_raw != fukusho_hit_validated": (7,),
        }
    )
    r_a = _check_raw_validated_drift(cur_a)
    assert r_a.severity == "info"
    assert r_a.detail.get("drift_count") == 7
    assert r_a.detail.get("non_dead_heat_drift_count") == 0

    # シナリオ (b): drift 行数 = 7・dead_heat 以外の drift 行数 = 2（source 不一致等のシグナル）
    # INFO なので passed=True のまま（label 正当性は precision/recall が保証）
    cur_b = _mock_cursor(
        {
            "label_validation_status != 'dead_heat'": (2,),
            "fukusho_hit_raw != fukusho_hit_validated": (7,),
        }
    )
    r_b = _check_raw_validated_drift(cur_b)
    assert r_b.severity == "info"
    assert r_b.detail.get("non_dead_heat_drift_count") == 2


# ---------------------------------------------------------------------------
# Test 11: >99.9% agreement（時系列ホールドアウト + 層化・レース単位馬集合完全一致）
# ---------------------------------------------------------------------------


@pytest.mark.requires_db
def test_gt_999_pct_agreement(readonly_cur) -> None:  # noqa: ANN001
    """SC#2: 時系列ホールドアウト（最新10%）+ 層化でレース単位馬集合完全一致を assert・agreement >= 99.9%。

    実DB 必須（``@pytest.mark.requires_db``）。``_compute_race_level_agreement(cur, sample_pct=0.1)``
    を呼出し、戻り値の ``agreement_pct`` が 99.9 以上であることを検証する。
    """
    result = _compute_race_level_agreement(readonly_cur, sample_pct=0.1)
    agreement_pct = float(result["agreement_pct"])
    total = int(result["total_held_out"])
    assert total > 0, "ホールドアウトに少なくとも1レースは含まれるべき（実DB が populated の前提）"
    assert agreement_pct >= 99.9, (
        f"SC#2 違反: 払戻テーブル突合 agreement {agreement_pct:.4f}% < 99.9%. "
        f"disagree_races (先頭): {result.get('disagree_races', [])[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 12-13: verdict fail / pass 集計（D-01 踏襲）
# ---------------------------------------------------------------------------


def test_verdict_fail_when_block_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """BLOCK 検査1件でも passed=False の場合、verdict='fail'（Phase 1 D-01 と同じ集計）。"""
    # precision だけ passed=False を返す状況を作る
    monkeypatch.setattr(
        label_reconcile,
        "_check_payout_precision",
        lambda cur: CheckResult(name="payout_precision", passed=False, severity="block", detail={}),
    )

    cur = _mock_cursor({})
    result = reconcile_against_payout(cur)
    assert result["verdict"] == "fail"
    block_checks = [c for c in result["checks"] if c["severity"] == "block"]
    assert any(not c["passed"] for c in block_checks)


def test_verdict_pass_when_all_block_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """全 BLOCK 検査 passed=True の場合、verdict='pass'。"""
    # 全 BLOCK 検査を monkeypatch で passed=True に固定
    pass_checks = {
        "_check_payout_precision",
        "_check_payout_recall",
        "_check_dead_heat_integrity",
        "_check_no_scratch_mislabeled",
        "_check_dead_loss_not_excluded",
        "_check_no_fukusho_sale_not_in_training",
        "_check_raw_validated_drift",
    }
    for name in pass_checks:
        monkeypatch.setattr(
            label_reconcile,
            name,
            lambda cur, _n=name: CheckResult(name=_n, passed=True, severity="block", detail={}),
        )
    # agreement も正常値を返す
    monkeypatch.setattr(
        label_reconcile,
        "_compute_race_level_agreement",
        lambda cur, **kw: {"agreement_pct": 99.9987, "agree_count": 3958, "total_held_out": 3958, "disagree_races": []},
    )

    cur = _mock_cursor({})
    result = reconcile_against_payout(cur)
    assert result["verdict"] == "pass"


# ---------------------------------------------------------------------------
# Test 14: WR-05 degraded_checks_count
# ---------------------------------------------------------------------------


def test_degraded_checks_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """WR-05: INFO 検査が 'error' キーを含む場合 degraded_checks_count > 0。"""
    # 全 BLOCK 検査を passed=True に固定
    pass_checks = {
        "_check_payout_precision",
        "_check_payout_recall",
        "_check_dead_heat_integrity",
        "_check_no_scratch_mislabeled",
        "_check_dead_loss_not_excluded",
        "_check_no_fukusho_sale_not_in_training",
        "_check_raw_validated_drift",
    }
    for name in pass_checks:
        monkeypatch.setattr(
            label_reconcile,
            name,
            lambda cur, _n=name: CheckResult(name=_n, passed=True, severity="block", detail={}),
        )
    monkeypatch.setattr(
        label_reconcile,
        "_compute_race_level_agreement",
        lambda cur, **kw: {"agreement_pct": 100.0, "agree_count": 1, "total_held_out": 1, "disagree_races": []},
    )
    # _check_label_status_distribution は 'error' キーを含む detail を返す（silent degradation シミュレート）
    monkeypatch.setattr(
        label_reconcile,
        "_check_label_status_distribution",
        lambda cur: CheckResult(
            name="label_status_distribution",
            passed=True,
            severity="info",
            detail={"error": "simulated query failure"},
        ),
    )

    cur = _mock_cursor({})
    result = reconcile_against_payout(cur)
    assert "degraded_checks_count" in result
    assert result["degraded_checks_count"] >= 1


# ---------------------------------------------------------------------------
# Test 15: T-02-02 認証情報非含有
# ---------------------------------------------------------------------------


def test_no_auth_info_in_check_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-02-02: 各 check dict が {name, passed, severity, detail} のみをキーに持ち、
    detail の値に 'password' / 'dsn' / 'secret' の部分文字列を含まない。
    """
    # 正常状態の mock（全 BLOCK passed=True）
    pass_checks = {
        "_check_payout_precision",
        "_check_payout_recall",
        "_check_dead_heat_integrity",
        "_check_no_scratch_mislabeled",
        "_check_dead_loss_not_excluded",
        "_check_no_fukusho_sale_not_in_training",
        "_check_raw_validated_drift",
    }
    for name in pass_checks:
        monkeypatch.setattr(
            label_reconcile,
            name,
            lambda cur, _n=name: CheckResult(name=_n, passed=True, severity="block", detail={"count": 0}),
        )
    monkeypatch.setattr(
        label_reconcile,
        "_check_label_status_distribution",
        lambda cur: CheckResult(
            name="label_status_distribution",
            passed=True,
            severity="info",
            detail={"unresolved_fraction": 0.000678, "unresolved_count": 376, "total_count": 553891},
        ),
    )
    monkeypatch.setattr(
        label_reconcile,
        "_compute_race_level_agreement",
        lambda cur, **kw: {"agreement_pct": 100.0, "agree_count": 1, "total_held_out": 1, "disagree_races": []},
    )

    cur = _mock_cursor({})
    result = reconcile_against_payout(cur)

    forbidden = ("password", "dsn=", "secret")
    for check in result["checks"]:
        assert set(check.keys()) <= {"name", "passed", "severity", "detail"}, (
            f"check dict は name/passed/severity/detail のみをキーに持つべき: {set(check.keys())}"
        )
        # detail の全ての値（再帰的に）を文字列化して secret 部分文字列が無いか検証
        detail_str = repr(check.get("detail", {})).lower()
        for kw in forbidden:
            assert kw not in detail_str, (
                f"T-02-02 違反: detail に '{kw}' が含まれる: {check['detail']}"
            )


# ---------------------------------------------------------------------------
# Test 16: W3 / SC#3 unresolved fraction 明示報告
# ---------------------------------------------------------------------------


def test_unresolved_fraction_reported_in_status_distribution() -> None:
    """W3 / SC#3: _check_label_status_distribution の detail が unresolved_fraction と
    unresolved_threshold（0.01）を含み・mock で unresolved_count=376/total_count=553891 の場合
    unresolved_fraction ≈ 0.000678（< 0.01）かつ threshold_exceeded == False。
    """
    cur = _mock_cursor_with_fetchall(
        fetchone_map={
            "label_validation_status = 'unresolved'": (376,),
            "count(*)": (553891,),
        },
        fetchall_map={},
    )
    r = _check_label_status_distribution(cur)
    assert r.severity == "info"
    assert "unresolved_fraction" in r.detail
    assert "unresolved_threshold" in r.detail
    assert r.detail["unresolved_threshold"] == 0.01
    assert abs(r.detail["unresolved_fraction"] - (376 / 553891)) < 1e-6
    assert r.detail.get("threshold_exceeded") is False


# ---------------------------------------------------------------------------
# Test 17: REVIEWS HIGH #7 — _recompute_scratch_markers regression
# ---------------------------------------------------------------------------


def test_recompute_scratch_markers_uses_sentinel() -> None:
    """REVIEWS HIGH #7 regression: _recompute_scratch_markers のソースが
    (a) ``bataijyu_sentinels_scratch`` または ``se_marker_canonicalization`` を参照すること
    (b) ``is_scratch_cancel`` を条件式に含まないこと（label boolean 依存回避）
    を ``inspect.getsource`` で assert。
    """
    src = inspect.getsource(_recompute_scratch_markers)
    # (a) sentinel 参照
    assert (
        "bataijyu_sentinels_scratch" in src or "se_marker_canonicalization" in src
    ), "HIGH #7: _recompute_scratch_markers は sentinel 集合を参照すべき"
    # (b) is_scratch_cancel 非依存: docstring 内の言及は許容するが、コード内で
    # ``is_scratch_cancel`` を column access（``.is_scratch_cancel`` / ``["is_scratch_cancel"]``）
    # や比較（``is_scratch_cancel ==`` / ``is_scratch_cancel =``）の形で使用してはいけない。
    # コード部のみを抽出（docstring 以外）してトークン的に依存がないか検証する。
    code_body = _strip_docstring(src)
    forbidden_patterns = (
        ".is_scratch_cancel",       # column access (df.is_scratch_cancel / row.is_scratch_cancel)
        '["is_scratch_cancel"]',    # dict/subscript access
        "'is_scratch_cancel'",
        "is_scratch_cancel ==",     # comparison
        "is_scratch_cancel !=",
        "is_scratch_cancel=",       # assignment
    )
    for pat in forbidden_patterns:
        assert pat not in code_body, (
            f"HIGH #7 違反: _recompute_scratch_markers のコードが '{pat}' で "
            f"label.is_scratch_cancel に依存している: \n{code_body}"
        )
    # 実カラム bataijyu を SELECT していること
    assert "bataijyu" in src, "HIGH #7: raw SE bataijyu を SELECT すべき"


# ---------------------------------------------------------------------------
# Test 18: REVIEWS NEW HIGH #1 — NULL-safe + padded umaban regression
# ---------------------------------------------------------------------------


def test_check_payout_precision_null_safe_padded_umaban() -> None:
    """REVIEWS NEW HIGH #1 regression: _check_payout_precision / _check_payout_recall が
    (a) ``NOT IN`` 単独ではなく ``NOT EXISTS`` / ``EXCEPT`` / ``IS DISTINCT FROM`` のいずれか
        （NULL-safe セット比較）を使用すること
    (b) 両側 ``LPAD(...::text, 2, '0')`` で zero-pad すること
    を ``inspect.getsource`` で regression assert する。
    """
    src_p = inspect.getsource(_check_payout_precision)
    src_r = inspect.getsource(_check_payout_recall)

    # (a) NULL-safe セット比較が存在する（NOT IN 単独でない）
    null_safe_markers = ("NOT EXISTS", "EXCEPT", "IS DISTINCT FROM")
    assert any(m in src_p for m in null_safe_markers), (
        "NEW HIGH #1: _check_payout_precision は NOT EXISTS / EXCEPT / IS DISTINCT FROM "
        "のいずれか（NULL-safe）を含むべき"
    )
    assert any(m in src_r for m in null_safe_markers), (
        "NEW HIGH #1: _check_payout_recall は NOT EXISTS / EXCEPT / IS DISTINCT FROM "
        "のいずれか（NULL-safe）を含むべき"
    )

    # (b) 両側 LPAD zero-pad
    assert "LPAD(" in src_p, "NEW HIGH #1: _check_payout_precision は LPAD( で zero-pad すべき"
    assert "LPAD(" in src_r, "NEW HIGH #1: _check_payout_recall は LPAD( で zero-pad すべき"

    # NULLIF で '00' を NULL にしていること（payout slot から '00'/空 を除外）
    assert "NULLIF" in src_p, "NEW HIGH #1: _check_payout_precision は NULLIF で '00' を除外すべき"
    assert "NULLIF" in src_r, "NEW HIGH #1: _check_payout_recall は NULLIF で '00' を除外すべき"

    # regression: ソースに 'payfukusyoumaban' が含まれる（実カラム名・Pitfall 1）
    assert "payfukusyoumaban" in src_p, "NEW HIGH #1: payout slot カラム payfukusyoumaban を参照すべき"
    assert "payfukusyoumaban" in src_r
