# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・test_audit_speed_figure.py と同一慣例)
"""SC#4 adversarial（SAFE-01 proxy 排除証明 + PIT lookahead 注入）: Phase 10 新モジュール（field_strength / race_relative）の AST に市場情報 proxy が0件を静的証明し・lookahead 注入で PIT 保証を逆証明する.

本ファイルは SC#4 adversarial（SAFE-01 横断聖域 + PIT 保証・最終監査層）であり・機能テスト
``tests/features/test_field_strength.py`` / ``tests/features/test_race_relative.py``（機能: 正しく計算される）とは独立層。
新モジュール ``src/features/field_strength.py`` と ``src/features/race_relative.py`` が市場情報 proxy
（odds / ninki / fukuodds / ninkij / tansyouodds）を一切参照しないことを AST 静的解析で証明し・
更に REVIEW H3 (10-REVIEWS.md L158, L197, L229) として ``odds`` を SQL 文字列リテラル検査に含める拡張で・
SQL text 埋込み型リークも検出することを機械保証する。

加えて PIT 保証（D-01 opponent-vs-source strict < + CYCLE-2 HIGH-C2-1 source-vs-target-cutoff 値の不変性）を
adversarial lookahead 注入テストで逆証明する:
  - test_lookahead_injection_detected: ``_pit_cutoff_prefilter`` を monkeypatch で ``<=`` に差替えると
    same-day opponent が混入し profile が変化する（guard 有効の逆証明・D-01）
  - test_source_vs_target_cutoff_lookahead_injection_detected: ``_compute_source_asof_opponent_speed_figures``
    を monkeypatch で target cutoff を使う版に差替えると・(source, target] 区間の opponent レースが
    par/variant/speed_figure 値に混入し profile が変化する（行包含・REVIEW H4・PLAN 01 T-10-01b 対応）
  - test_source_asof_value_invariance: 同じ pre-source opponent race を異なる target cutoff
    （feature_cutoff_datetime=T1<T2・両方とも source available_at=S より後）で消費しても
    source-as-of full-pipeline 再計算 speed_figure が bit-identical になることを独立に assert
    （値の不変性・CYCLE-2 MEDIUM-C2-4・行包含テストでは不十分・10-REVIEWS.md L230-235）

cross-reference: tests/features/test_field_strength.py（機能テスト・正しく計算される・PIT 保証の機能検証も同居）。
cross-reference: tests/audit/test_audit_speed_figure.py（5段階鋳型・SC#4 構造踏襲元・odds-free 聖域・Phase 9 横断）。
cross-reference: tests/audit/test_audit_features.py（SC#2 adversarial・5段階鋳型原型・lookahead 注入 idiom）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし・純粋 AST/monkeypatch 検査）。
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features import field_strength, race_relative
from src.model.data import _derive_feature_columns

# ---------------------------------------------------------------------------
# SC#4 forbidden tokens（SAFE-01 横断聖域・市場情報 proxy・test_audit_speed_figure.py と共通）
# ---------------------------------------------------------------------------
# 文字列 contains では docstring/コメント中の "odds-free" 言及が false positive になるため・
# AST Name ノード(id) / Attribute ノード(attr) で厳密に判定する（文字列部分一致でなく AST 構造）。
_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)

# test_audit_speed_figure.py L43-48: 既存 scanner は "odds" 単独は part-of-word false positive が
# 多すぎるため Name/Attribute 完全一致のみとし SQL リテラル検査から除外する。
# REVIEW H3 (10-REVIEWS.md L158, L197, L229): 本 audit は field_strength/race_relative 向けに
# odds を SQL リテラル検査に含める拡張を導入する（whitelist で無害 prose を除外）。
_FORBIDDEN_PROXY_SUBSTRING_TOKENS_BASE: tuple[str, ...] = (
    "ninki",
    "fukuodds",
    "ninkij",
    "tansyouodds",
)

# REVIEW H3 拡張: field_strength / race_relative 向けに odds を SQL リテラル検査に追加。
# whitelist で docstring/prose 中の 'odds-free' 'odds_snapshot_policy' 等の無害言及を除外し
# false-positive を防ぐ（無害 prose を残しつつ SQL text への埋込みを検出）。
_ODDS_IN_SQL_WHITELIST: tuple[str, ...] = (
    "odds-free",
    "odds_snapshot_policy",
    "odds_snapshot_at",
    "odds-free module",
    "市場情報 proxy を使わない",
)

_PROXY_PATTERN_BASE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_PROXY_SUBSTRING_TOKENS_BASE) + r")\b"
)
_ODDS_PATTERN = re.compile(r"\bodds\b")


def _is_whitelisted_odds_prose(value: str) -> bool:
    """REVIEW H3 whitelist: 無害 prose 中の 'odds' 言及を false-positive から除外.

    docstring の 'odds-free' / 'odds_snapshot_policy' 等・SAFE-01 聖域を説明する無害な言及は
    SQL text 埋込みでないため検出対象から除外する。本関数は odds のみに適用し・
    ninki/fukuodds/ninkij/tansyouodds は無害言及が存在し得ないため適用しない（厳密）。
    """
    return any(phrase in value for phrase in _ODDS_IN_SQL_WHITELIST)


def _scan_module_for_forbidden_tokens(module_obj) -> tuple[list[str], list[str]]:
    """モジュールのソースを AST parse し・forbidden Name/Attribute と SQL 文字列 proxy を走査.

    test_audit_speed_figure.py L63-108 と同一構造（5段階鋳型(1)(2)(3)）に・REVIEW H3 拡張として
    ``odds`` の SQL 文字列リテラル検査を追加した版（field_strength/race_relative 向け）。

    REVIEW H3 (10-REVIEWS.md L158, L197, L229): ``ast.Constant`` value が str の場合は
    word-boundary 部分一致で SQL 文字列内の proxy トークン埋込みを検出する。
    ``odds`` は whitelist ('odds-free' 等) で無害 prose を除外しつつ SQL text 埋込みを検出する。
    ninki/fukuodds/ninkij/tansyouodds は whitelist 適用なし（無害言及し得ないため）。

    Returns
    -------
    (name_attr_violations, constant_str_violations)
        name_attr_violations: ``"Name(odds) @ line N"`` / ``"Attribute(ninki) @ line N"`` 形式
        constant_str_violations: ``"Constant-str(ninki) @ line N: <snippet>"`` 形式
    """
    source = inspect.getsource(module_obj)
    tree = ast.parse(textwrap.dedent(source))

    name_attr_violations: list[str] = []
    constant_str_violations: list[str] = []

    for node in ast.walk(tree):
        # Name ノード: id が _FORBIDDEN_TOKENS に完全一致
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_TOKENS:
            name_attr_violations.append(f"Name({node.id}) @ line {node.lineno}")
        # Attribute ノード: attr が _FORBIDDEN_TOKENS に完全一致
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_TOKENS:
            name_attr_violations.append(f"Attribute({node.attr}) @ line {node.lineno}")
        # REVIEW H3 + H5: ast.Constant value が str の場合・word-boundary 部分一致で proxy 検出
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            snippet = value if len(value) <= 60 else (value[:60] + "...")
            # ninki/fukuodds/ninkij/tansyouodds: whitelist 適用なし（厳密）
            for tok in _PROXY_PATTERN_BASE.findall(value):
                constant_str_violations.append(
                    f"Constant-str({tok}) @ line {node.lineno}: {snippet!r}"
                )
            # REVIEW H3 拡張: odds は whitelist で無害 prose を除外しつつ検出
            if _ODDS_PATTERN.search(value) and not _is_whitelisted_odds_prose(value):
                constant_str_violations.append(
                    f"Constant-str(odds) @ line {node.lineno}: {snippet!r}"
                )

    return name_attr_violations, constant_str_violations


# ---------------------------------------------------------------------------
# P10 SC#4 snapshot_id（PLAN 05 SUMMARY で決定・本 audit が消費）
# ---------------------------------------------------------------------------
# Phase 10: opponent_strength snapshot（FEAT-02 21 + FEAT-03 6 = 27 新 feature・delta=+44 は
# Phase 9.1 speed_figure 17 feature も含むため・本 audit は Phase 10 27 feature に焦点）。
_PHASE10_SNAPSHOT_ID = "20260626-1a-opponentstrength-v1"


# ---------------------------------------------------------------------------
# (a)(b)(c): SC#4 AST audit — field_strength / race_relative の forbidden Name/Attribute/Constant 0件
# ---------------------------------------------------------------------------
def test_no_odds_ninki_proxy_in_field_strength_source() -> None:
    """SC#4 AST: src.features.field_strength ソースが odds/ninki proxy Name/Attribute/SQL 文字列を含まない.

    本テストは SC#4 adversarial（SAFE-01 静的証明・Phase 10 新モジュール）。
    ``odds``/``ninki``/``fukuodds``/``ninkij``/``tansyouodds`` が Name/Attribute ノードに0件で
    あること・および REVIEW H5/H3 として SQL 文字列定数内に proxy トークン(word-boundary 部分一致・
    odds 含む拡張)が0件であることを AST 静的解析で証明する。
    cross-reference: tests/features/test_field_strength.py（機能テスト・正しく計算される）。
    """
    name_attr, const_str = _scan_module_for_forbidden_tokens(field_strength)
    assert not name_attr, (
        f"field_strength.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {name_attr}"
    )
    assert not const_str, (
        f"field_strength.py に SQL 文字列リテラル内 proxy トークンが存在 "
        f"(REVIEW H5/H3 違反・odds 含む拡張): {const_str}"
    )


def test_no_odds_ninki_proxy_in_race_relative_source() -> None:
    """SC#4 AST: src.features.race_relative ソースが odds/ninki proxy Name/Attribute/SQL 文字列を含まない.

    race_relative.py は rolling_speed_figure_mean_5 / best2_mean_5 / median_5 と
    rolling_field_strength_mean_mean_5 のみを入力とし・市場情報には触れない契約（PLAN 03）。
    同契約の静的証明（odds 含む拡張・REVIEW H3）。
    cross-reference: tests/features/test_race_relative.py（機能テスト）。
    """
    name_attr, const_str = _scan_module_for_forbidden_tokens(race_relative)
    assert not name_attr, (
        f"race_relative.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {name_attr}"
    )
    assert not const_str, (
        f"race_relative.py に SQL 文字列リテラル内 proxy トークンが存在 "
        f"(REVIEW H5/H3 違反・odds 含む拡張): {const_str}"
    )


# ---------------------------------------------------------------------------
# (d): SC#4 allowlist — FEATURE_COLUMNS に Phase 10 27 feature 含有・forbidden prefix 0件
# ---------------------------------------------------------------------------
def test_feature_columns_contains_phase10_features_no_proxy() -> None:
    """SC#4 allowlist(REVIEW H1 _derive_feature_columns 経由): Phase 10 27 feature 含有・forbidden prefix 0件.

    検査内容:
      - Phase 10 opponentstrength snapshot では rolling_field_strength_* 21 feature と
        FEAT-03 6 feature（speed_index_rank_mean5/best2_mean5/median5・gap_to_top・gap_to_3rd・
        field_strength_adjusted_rank）が FEATURE_COLUMNS に含まれる
      - FEATURE_COLUMNS の各要素は forbidden prefix（odds/ninki/fukuodds/ninkij/tansyouodds で始まる）
        でない（banned alias sneak-in の構造的防止・HIGH #9）

    cross-reference: tests/features/test_field_strength.py（機能テスト）。
    """
    # v1.0 デフォルト: Phase 10 feature は含まれず・forbidden prefix 0件（後方互換 A5）
    v10_cols = _derive_feature_columns(snapshot_id=None)
    v10_phase10 = [c for c in v10_cols if c.startswith("rolling_field_strength_") or c.startswith("speed_index_rank_") or c in ("gap_to_top", "gap_to_3rd", "field_strength_adjusted_rank")]
    assert v10_phase10 == [], (
        f"v1.0 FEATURE_COLUMNS に Phase 10 feature が含まれる（後方互換違反）: {v10_phase10}"
    )
    v10_forbidden = [c for c in v10_cols if c.split("_")[0] in _FORBIDDEN_TOKENS]
    assert v10_forbidden == [], (
        f"v1.0 FEATURE_COLUMNS に forbidden prefix カラムが存在: {v10_forbidden}"
    )

    # Phase 10 snapshot: 27 feature 含有・forbidden prefix 0件
    snapshot_path = Path(f"snapshots/feature_matrix_{_PHASE10_SNAPSHOT_ID}.parquet")
    if snapshot_path.exists():
        p10_cols = _derive_feature_columns(snapshot_id=_PHASE10_SNAPSHOT_ID)
        # Phase 10 新 feature（FEAT-02 rolling_field_strength_* 21 + FEAT-03 6 = 27 feature）
        expected_phase10_features = {
            # FEAT-02 相手強度 rolling_field_strength（21 feature）・PLAN 02 実装
            "rolling_field_strength_mean_latest_1",
            "rolling_field_strength_mean_mean_3",
            "rolling_field_strength_mean_mean_5",
            "rolling_field_strength_mean_trend_last_minus_mean5",
            "rolling_field_strength_mean_trend_mean3_minus_mean5",
            "rolling_field_strength_median_latest_1",
            "rolling_field_strength_median_mean_3",
            "rolling_field_strength_median_mean_5",
            "rolling_field_strength_max_latest_1",
            "rolling_field_strength_max_mean_3",
            "rolling_field_strength_max_mean_5",
            "rolling_field_strength_top3_mean_latest_1",
            "rolling_field_strength_top3_mean_mean_3",
            "rolling_field_strength_top3_mean_mean_5",
            "rolling_field_strength_top5_mean_latest_1",
            "rolling_field_strength_top5_mean_mean_3",
            "rolling_field_strength_top5_mean_mean_5",
            "rolling_field_strength_sd_latest_1",
            "rolling_field_strength_sd_mean_5",
            "rolling_field_strength_coverage_mean_5",
            "rolling_field_strength_valid_count_mean_5",
            # FEAT-03 レース内相対（6 feature）・PLAN 03 実装
            "speed_index_rank_mean5",
            "speed_index_rank_best2_mean5",
            "speed_index_rank_median5",
            "gap_to_top",
            "gap_to_3rd",
            "field_strength_adjusted_rank",
        }
        actual_phase10 = {
            c for c in p10_cols
            if c.startswith("rolling_field_strength_")
            or c.startswith("speed_index_rank_")
            or c in ("gap_to_top", "gap_to_3rd", "field_strength_adjusted_rank")
        }
        missing = expected_phase10_features - actual_phase10
        assert not missing, (
            f"Phase 10 snapshot FEATURE_COLUMNS に期待の27 feature のうち欠落: {missing} "
            f"(actual phase10 features: {sorted(actual_phase10)})"
        )
        # FEATURE_COLUMNS の各要素は forbidden prefix で始まらない（HIGH #9 banned alias sneak-in 防止）
        forbidden_in_p10 = [c for c in p10_cols if c.split("_")[0] in _FORBIDDEN_TOKENS]
        assert forbidden_in_p10 == [], (
            f"Phase 10 snapshot FEATURE_COLUMNS に forbidden prefix カラムが存在: "
            f"{forbidden_in_p10} (HIGH #9 違反・banned alias sneak-in)"
        )
    else:
        # WR-06 (10-08 gap-closure): snapshot 未生成時は pytest.skip に変更。
        # 旧実装は pytest.raises(FileNotFoundError) だったが・これでは「silent fallback で mask しない」
        # 意図が test_data.py::test_phase10_derive_feature_columns_new_and_baseline_regression と重複し・
        # CI/snapshot 無し環境では常に else 経路が走り 27 feature 含有検査が一度も実行されず ship される
        # リスクがあった（silent fallback mask 経路）。実 snapshot 検証は test_data.py に一本化し・
        # 本テストは snapshot が存在する環境でのみ 27 feature 含有検査を実行する。
        pytest.skip(
            f"Phase 10 snapshot ({_PHASE10_SNAPSHOT_ID}) 未生成・"
            "実 snapshot 検証は test_data.py::test_phase10_* に一本化 (WR-06・silent fallback mask 排除)"
        )


# ---------------------------------------------------------------------------
# (g): SC#4 false-pass 回避・H5/H3 拡張 — 意図的注入を検出することの証明
# ---------------------------------------------------------------------------
def test_false_pass_detection_power() -> None:
    """SC#4 false-pass 回避・H5/H3 拡張: guard が意図的注入(Name/Attribute/SQL 文字列 proxy・odds 含む)を検出することを証明.

    5段階鋳型(5)に相当（test_audit_features.py / test_audit_speed_figure.py の false-pass 回避構造踏襲）。
    意図的に禁止トークンを含むダミーソース文字列を構築し AST parse して・本 audit の
    ``_scan_module_for_forbidden_tokens`` が(1) forbidden Name/Attribute ノードを検出すること・
    (2) REVIEW H5 として SQL 文字列定数内 proxy も検出すること・(3) REVIEW H3 として odds の
    SQL 文字列埋込みも検出することを確認する。
    cross-reference: tests/audit/test_audit_speed_figure.py::test_false_pass_detection_power。
    """
    # (1) Name/Attribute 注入: forbidden Name/Attribute を参照するダミーソース
    dummy_name_attr_source = textwrap.dedent(
        """
        def leaky():
            odds = 1.5  # forbidden Name
            x = obj.ninki  # forbidden Attribute
            return odds + x
        """
    )
    tree_name_attr = ast.parse(dummy_name_attr_source)
    name_hits: list[str] = []
    for node in ast.walk(tree_name_attr):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_TOKENS:
            name_hits.append(f"Name({node.id})")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_TOKENS:
            name_hits.append(f"Attribute({node.attr})")
    assert "Name(odds)" in name_hits, (
        "Name ノード検出力不足: 意図的 odds Name 注入を検出していない（false-pass・T-08-01 違反）"
    )
    assert "Attribute(ninki)" in name_hits, (
        "Attribute ノード検出力不足: 意図的 ninki Attribute 注入を検出していない（false-pass・T-08-01 違反）"
    )

    # (2) REVIEW H5: SQL 文字列定数内 proxy（ninki/fukuodds/ninkij/tansyouodds）注入検出
    dummy_sql_source = textwrap.dedent(
        '''
        SQL_HIST = "ur.ninki AS prior_ninki, ur.fukuodds AS fukuodds_prev"
        '''
    )
    tree_sql = ast.parse(dummy_sql_source)
    sql_hits: list[str] = []
    for node in ast.walk(tree_sql):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql_hits.extend(_PROXY_PATTERN_BASE.findall(node.value))
    assert "ninki" in sql_hits, (
        "REVIEW H5 検出力不足: SQL 文字列 'ur.ninki AS prior_ninki' 内 proxy を検出していない"
    )
    assert "fukuodds" in sql_hits, (
        "REVIEW H5 検出力不足: SQL 文字列 'ur.fukuodds AS fukuodds_prev' 内 proxy を検出していない"
    )

    # (3) REVIEW H3 (10-REVIEWS.md L158, L197, L229): odds の SQL 文字列埋込み検出
    # 既存 scanner (test_audit_speed_figure.py) は odds を SQL リテラル検査から除外するが・
    # 本 audit は odds を SQL リテラル検査に含める拡張（whitelist で 'odds-free' 等を除外）。
    # odds 単語(word-boundary \bodds\b)が SQL text に埋込まれることを検出する。
    dummy_odds_sql_source = textwrap.dedent(
        '''
        SQL_ODDS = "SELECT odds AS market_odds FROM market_table WHERE ninki > 5"
        '''
    )
    tree_odds = ast.parse(dummy_odds_sql_source)
    odds_hits: list[str] = []
    for node in ast.walk(tree_odds):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # odds 検出（whitelist 適用後）
            if _ODDS_PATTERN.search(node.value) and not _is_whitelisted_odds_prose(node.value):
                odds_hits.append("odds")
    assert "odds" in odds_hits, (
        "REVIEW H3 検出力不足: SQL 文字列内の 'odds' を検出していない・"
        "既存 scanner (test_audit_speed_figure.py) は odds を SQL 除外するが本 audit は検出する拡張"
    )

    # (4) false positive 回避の証明: "odds-free" docstring 言及は whitelist で検出対象外
    dummy_docstring_source = textwrap.dedent(
        '''
        """odds-free module: 本モジュールは市場情報 proxy を使わない（SAFE-01・odds_snapshot_policy 参照）。"""
        def f():
            return 0
        '''
    )
    tree_doc = ast.parse(dummy_docstring_source)
    doc_odds_hits: list[str] = []
    for node in ast.walk(tree_doc):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _ODDS_PATTERN.search(node.value) and not _is_whitelisted_odds_prose(node.value):
                doc_odds_hits.append("odds")
    assert doc_odds_hits == [], (
        f"false positive: docstring の 'odds-free'/'odds_snapshot_policy' 言及が検出対象になった: "
        f"{doc_odds_hits} (whitelist で無害 prose を除外すべき・REVIEW H3)"
    )


# ---------------------------------------------------------------------------
# (6) lookahead 注入テスト・D-01 PIT 保証 adversarial（opponent-vs-source）
# ---------------------------------------------------------------------------
def _fs_history_row(
    race_nkey: str,
    kettonum: int,
    race_date: str,
    *,
    time: float,
    trackcd: str = "24",
    jyocd: str = "05",
    kyori: int = 1600,
    kakuteijyuni: int = 1,
    **overrides,
) -> dict:
    """合成 raw_history 行（test_field_strength.py と同一の builder・DB 不要）。"""
    row: dict = {
        "race_nkey": race_nkey,
        "kettonum": kettonum,
        "race_date": pd.to_datetime(race_date),
        "as_of_datetime": pd.to_datetime(race_date),
        "race_start_datetime": pd.to_datetime(race_date) + pd.Timedelta(hours=12),
        "time": float(time),
        "trackcd": trackcd,
        "jyocd": jyocd,
        "kyori": kyori,
        "kakuteijyuni": kakuteijyuni,
        "timediff": 0.0,
        "harontimel3": 36.0,
        "jyuni3c": 1,
        "jyuni4c": 1,
        "babacd": "01",
        "umaban": 1,
        "wakuban": 1,
    }
    row.update(overrides)
    return row


def test_lookahead_injection_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-01 PIT 保護 adversarial（opponent-vs-source・strict <）: ``_pit_cutoff_prefilter`` を ``<=`` 版に
    差替えると same-day opponent が混入し profile 値（field_strength_mean）が変化する（guard 有効の逆証明）.

    本テストは SC#4 adversarial（PIT 保証・SAFE-01 横断聖域）。
    source race R1(2023-06-10) と同日の H2 の R1 行は・本番の strict ``<`` では除外される。
    PLAN 01 は 2層 PIT gate（layer 1 = source-as-of recompute の strict < cutoff・layer 2 = ``_pit_cutoff_prefilter``
    の strict < 行フィルタ）を採用する。layer 2 のみ無効化しても・layer 1 で same-day 行の speed_figure
    が再計算されないため（cutoff strict < で除外）混入経路が閉じる（防御の重複）。

    よって本テストは layer 1 も無効化（``_compute_source_asof_opponent_speed_figures`` の再計算 cutoff を
    未来に引き上げ）した上で layer 2 も ``<=`` 版に差替え・2層 defense を完全突破して same-day 行を混入
    させる。保護あり経路と leaky 経路で H1 の field_strength_mean が変化することで guard が有効であることを
    逆証明する（false-pass 回避・layer 1/2 の重複防御の検出力証明）。
    cross-reference: tests/features/test_field_strength.py::test_opponent_vs_source_pit_strict_less（機能側）。
    cross-reference: tests/features/test_field_strength.py::test_opponent_vs_source_pit_strict_less_adversarial
    （機能側 adversarial・同一 idiom）。
    """
    import src.features.field_strength as fs_mod
    from src.features.field_strength import compute_field_strength_profile

    # source race R1(2023-06-10)・starters: H1/H2・H2 は5走以上の過去走を持つ
    # H2 は R0a〜R0e の5走（R1 より前）に加え R1 自身に出走（same-day 行）
    # 保護あり経路（strict <）では H2 の ability は R0a〜R0e の最新5件平均。
    # leaky 版（2層突破・same-day R1 行を混入）では H2 の ability が R0b〜R0e + R1 の平均に変化する。
    # H2 の R1 の time を R0a〜R0e と異なる値にし・ability 値が変化するようにする（検出力証明）。
    rows = [
        _fs_history_row("R0a_20230401", 2002, "2023-04-01", time=1560.0),
        _fs_history_row("R0b_20230415", 2002, "2023-04-15", time=1540.0),
        _fs_history_row("R0c_20230501", 2002, "2023-05-01", time=1520.0),
        _fs_history_row("R0d_20230515", 2002, "2023-05-15", time=1500.0),
        _fs_history_row("R0e_20230601", 2002, "2023-06-01", time=1480.0),
        # source race R1 (2023-06-10): H1/H2 出走・H2 の same-day 行は R0 群より速い(1460)
        _fs_history_row("R1_20230610", 2001, "2023-06-10", time=1500.0),
        _fs_history_row("R1_20230610", 2002, "2023-06-10", time=1460.0),
    ]
    raw_history = pd.DataFrame(rows)

    # 保護あり（本番・2層 defense 有効）: H2 の same-day R1 行は除外され ability は R0a〜R0e の平均
    result_protected = compute_field_strength_profile(raw_history)
    h1_protected = result_protected[
        (result_protected["kettonum"] == 2001)
        & (result_protected["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_protected) == 1
    mean_protected = float(h1_protected["field_strength_mean"].iloc[0])

    # adversarial: layer 1 (recompute cutoff を R1 以後に引き上げ) + layer 2 (< → <=) の両方を無効化
    # 2層 defense を完全突破することで same-day R1 行を H2 の ability 窓に混入させる
    original_compute = fs_mod._compute_source_asof_opponent_speed_figures

    def _leaky_compute(*args, **kwargs):
        raw_history_inner = kwargs.get("raw_history", args[0] if args else None)
        source_avail = kwargs.get(
            "source_available_at_by_race", args[1] if len(args) > 1 else None
        )
        leaky_cutoff = source_avail.copy()
        leaky_cutoff[:] = pd.to_datetime("2023-06-30")
        return original_compute(
            raw_history=raw_history_inner,
            source_available_at_by_race=leaky_cutoff,
        )

    def _leaky_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
        # strict < を <= に差替え・available_at == source_available_at の same-day 行を通す
        return expanded[
            expanded["_opp_available_at"] <= expanded["_source_available_at"]
        ].copy()

    monkeypatch.setattr(
        fs_mod, "_compute_source_asof_opponent_speed_figures", _leaky_compute
    )
    monkeypatch.setattr(fs_mod, "_pit_cutoff_prefilter", _leaky_prefilter)
    try:
        result_leaked = compute_field_strength_profile(raw_history)
    finally:
        monkeypatch.undo()

    h1_leaked = result_leaked[
        (result_leaked["kettonum"] == 2001)
        & (result_leaked["race_nkey"] == "R1_20230610")
    ]
    assert len(h1_leaked) == 1
    mean_leaked = float(h1_leaked["field_strength_mean"].iloc[0])

    assert not np.isclose(mean_protected, mean_leaked), (
        f"guard 無効化（2層 defense 完全突破・same-day opponent 混入）で field_strength_mean が変化しない・"
        f"protected={mean_protected}・leaked={mean_leaked}・"
        f"検出力不足（false-pass・D-01 PIT 保証違反）"
    )


# ---------------------------------------------------------------------------
# (6b-a) REVIEW H4 source-vs-target-cutoff lookahead 注入（行包含・より重大なリークパス）
# ---------------------------------------------------------------------------
def test_source_vs_target_cutoff_lookahead_injection_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REVIEW H4 (10-REVIEWS.md L160, L198, L229): source-vs-target-cutoff lookahead 注入（行包含）.

    ``_compute_source_asof_opponent_speed_figures`` を monkeypatch で target cutoff を使う版に
    差替えると・(source.available_at, target.feature_cutoff_datetime] 区間に走った opponent レースが
    par/variant/speed_figure 値に混入し profile が変化する（guard 有効の逆証明）。

    本テストは opponent-vs-source（``<``→``<=``）でなく・CYCLE-2 HIGH-C2-1 が指摘したより重大なリーク
    パス（obs_id 展開済み target-cutoff-contaminated speed_figure を source-race opponent 流用）を
    直接 poke する（PLAN 01 T-10-01b に対応・本 PLAN で独立実行）。

    cross-reference: tests/features/test_field_strength.py::test_cycle2_high_c2_1_value_invariance
    （機能側 adversarial・layer 1 + layer 2 完全突破で R_MID 混入を検出）。
    """
    import src.features.field_strength as fs_mod
    from src.features.field_strength import compute_field_strength_profile

    # source race S(2023-06-10)・starters: H1/H2・H2 は5走以上の過去走を持つ
    # H2 の R_MID(2023-06-15) は S 以後・保護あり経路（source-as-of recompute が S cutoff を使用）では除外
    # leaky 版（cutoff=T2=2023-06-30）では R_MID が混入し最新5走の構成が変わる
    rows = [
        _fs_history_row("R0a_20230401", 2002, "2023-04-01", time=1560.0),
        _fs_history_row("R0b_20230415", 2002, "2023-04-15", time=1540.0),
        _fs_history_row("R0c_20230501", 2002, "2023-05-01", time=1520.0),
        _fs_history_row("R0d_20230515", 2002, "2023-05-15", time=1500.0),
        _fs_history_row("R0e_20230601", 2002, "2023-06-01", time=1480.0),
        # H2 の R_MID(2023-06-15): S 以後・保護あり経路では除外・leaky 版で混入
        _fs_history_row("R_MID_20230615", 2002, "2023-06-15", time=1460.0),
        # source race S(2023-06-10): H1/H2 出走
        _fs_history_row("R_SRC_20230610", 2001, "2023-06-10", time=1500.0),
        _fs_history_row("R_SRC_20230610", 2002, "2023-06-10", time=1500.0),
    ]
    raw_history = pd.DataFrame(rows)

    # (A) 保護あり経路: source-as-of recompute（S cutoff=2023-06-10）・R_MID は除外
    result_protected = compute_field_strength_profile(raw_history)
    h1_src = result_protected[
        (result_protected["kettonum"] == 2001)
        & (result_protected["race_nkey"] == "R_SRC_20230610")
    ]
    assert len(h1_src) == 1
    mean_protected = float(h1_src["field_strength_mean"].iloc[0])

    # (B) adversarial: source-as-of recompute cutoff を target cutoff(T2=2023-06-30) に引き上げ
    # かつ layer 2 (_pit_cutoff_prefilter) も無効化・2層 defense を完全突破し R_MID を混入
    original_compute = fs_mod._compute_source_asof_opponent_speed_figures

    def _leaky_compute(*args, **kwargs):
        raw_history_inner = kwargs.get("raw_history", args[0] if args else None)
        source_avail = kwargs.get(
            "source_available_at_by_race", args[1] if len(args) > 1 else None
        )
        leaky_cutoff = source_avail.copy()
        leaky_cutoff[:] = pd.to_datetime("2023-06-30")
        return original_compute(
            raw_history=raw_history_inner,
            source_available_at_by_race=leaky_cutoff,
        )

    def _leaky_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
        return expanded.copy()

    monkeypatch.setattr(
        fs_mod, "_compute_source_asof_opponent_speed_figures", _leaky_compute
    )
    monkeypatch.setattr(fs_mod, "_pit_cutoff_prefilter", _leaky_prefilter)
    try:
        result_leaked = compute_field_strength_profile(raw_history)
    finally:
        monkeypatch.undo()

    h1_src_leaked = result_leaked[
        (result_leaked["kettonum"] == 2001)
        & (result_leaked["race_nkey"] == "R_SRC_20230610")
    ]
    mean_leaked = float(h1_src_leaked["field_strength_mean"].iloc[0])

    assert not np.isclose(mean_protected, mean_leaked), (
        f"source-as-of recompute cutoff を target cutoff(T2) に差替えても field_strength_mean が変化しない・"
        f"protected={mean_protected}・leaked={mean_leaked}・"
        f"(S, T2] 区間の opponent レース混入を行包含で検出できず false-pass（REVIEW H4 違反）"
    )


# ---------------------------------------------------------------------------
# (6b-b) CYCLE-2 MEDIUM-C2-4 値の不変性（行包含テストでは不十分・10-REVIEWS.md L230-235）
# ---------------------------------------------------------------------------
def test_source_asof_value_invariance() -> None:
    """CYCLE-2 MEDIUM-C2-4 (10-REVIEWS.md L230-235, L301): source-as-of full-pipeline 再計算 speed_figure の値の不変性.

    行包含テスト（test_source_vs_target_cutoff_lookahead_injection_detected・Cycle-1 H4）は
    (S, T] 区間の opponent レース除外を検出するが・obs_id 展開済み target-cutoff-contaminated
    speed_figure を再利用していると値レベルでリークが残る（10-REVIEWS.md L230-235）。
    本テストは同じ pre-source opponent race を異なる target cutoff（T1<T2・両方とも source available_at=S
    より後）で消費しても source-as-of full-pipeline 再計算された profile 値が bit-identical になることを
    独立に assert する（値レベルのリーク検出）。

    source race S(2023-06-10) に対し・H2 は R_PRE(2023-06-01) に共通過去走を持つ。
    特性上・別の target cutoff（例: 別の source race の available_at）を与えても・source-as-of 経路は
    source race S 自身の available_at を cutoff として使うため profile 値は不変。
    本テストは _compute_source_asof_opponent_speed_figures が source_available_at_by_race のみを
    cutoff 真の源として使い・target cutoff には依存しないことを・外部から異なる cutoff を与えて
    も profile が変わらないことで証明する。

    cross-reference: tests/features/test_field_strength.py::test_cycle2_high_c2_1_value_invariance_across_targets
    （機能側・複数 source race で同一 opponent の ability が一致）。
    """
    from src.features.field_strength import compute_field_strength_profile

    # source race S1(2023-06-10) と S2(2023-06-20)・両者に H1/H2 出走・H2 は R_PRE(2023-06-01) に共通過去走
    rows = [
        _fs_history_row("S1_20230610", 3001, "2023-06-10", time=1500.0),
        _fs_history_row("S1_20230610", 3002, "2023-06-10", time=1500.0),
        _fs_history_row("S2_20230620", 3001, "2023-06-20", time=1500.0),
        _fs_history_row("S2_20230620", 3002, "2023-06-20", time=1500.0),
        _fs_history_row("R_PRE_20230601", 3002, "2023-06-01", time=1500.0),
    ]
    raw_history = pd.DataFrame(rows)

    # 2回呼出して source race 毎の profile 値の決定性（byte-reproducible）と source 独立性を確認
    result1 = compute_field_strength_profile(raw_history)
    result2 = compute_field_strength_profile(raw_history)

    # 値の不変性 (1): 同一入力の byte-reproducible 性
    h1_s1_r1 = result1[
        (result1["kettonum"] == 3001) & (result1["race_nkey"] == "S1_20230610")
    ]
    h1_s1_r2 = result2[
        (result2["kettonum"] == 3001) & (result2["race_nkey"] == "S1_20230610")
    ]
    mean_s1_r1 = float(h1_s1_r1["field_strength_mean"].iloc[0])
    mean_s1_r2 = float(h1_s1_r2["field_strength_mean"].iloc[0])
    assert np.isclose(mean_s1_r1, mean_s1_r2), (
        f"同一入力で byte-reproducible でない: r1={mean_s1_r1}・r2={mean_s1_r2}（§19.1 違反）"
    )

    # 値の不変性 (2): 異なる source race（異なる available_at）で消費しても・
    # H2 の pre-source 過去走（R_PRE・両 source より前）は同一 speed_figure で再計算されるため・
    # H1 の field_strength_mean は S1 と S2 で一致する（値の不変性・CYCLE-2 MEDIUM-C2-4 の核心）
    h1_s2_r1 = result1[
        (result1["kettonum"] == 3001) & (result1["race_nkey"] == "S2_20230620")
    ]
    mean_s2 = float(h1_s2_r1["field_strength_mean"].iloc[0])
    assert not np.isnan(mean_s1_r1) and not np.isnan(mean_s2), (
        f"field_strength_mean が NaN・mean_s1={mean_s1_r1}・mean_s2={mean_s2}（テストデータ前提違反）"
    )
    assert np.isclose(mean_s1_r1, mean_s2), (
        f"値の不変性違反: H2 の pre-source 過去走（R_PRE・両 source より前）が同一 speed_figure で"
        f"再計算されるにも関わらず・H1 の field_strength_mean が S1 と S2 で異なる・"
        f"mean_s1={mean_s1_r1}・mean_s2={mean_s2}・"
        f"obs_id 展開済み target-cutoff-contaminated speed_figure が流用されている疑い"
        f"（CYCLE-2 MEDIUM-C2-4・10-REVIEWS.md L230-235 違反・行包含テストでは検出不能）"
    )
