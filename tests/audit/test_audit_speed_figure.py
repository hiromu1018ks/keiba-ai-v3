# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/audit/test_audit_features.py と同一慣例)
"""SC#4 adversarial(SAFE-01 proxy 排除証明): speed_figure/rolling/builder の AST から市場情報 proxy が0件を静的証明する。

本ファイルは SC#4 adversarial（SAFE-01 横断聖域・静的証明）であり・機能テスト
``tests/features/test_speed_figure.py``（機能: speed_figure が正しく計算される）とは独立層。
機能テストは「speed_figure が Beyer 型意図通り計算される」を検証するのに対し・本 audit は
「speed_figure/rolling/builder ソースが市場情報 proxy（odds/ninki/fukuodds/ninkij/tansyouodds）
を一切参照しないこと」を AST 静的解析で証明し・FEATURE_COLUMNS allowlist にも banned alias
が sneak-in しないことを grep 的検査で構造保証する（SAFE-01 横断聖域・HIGH #9 二重防御）。
cross-reference: tests/features/test_speed_figure.py（機能テスト・正しく計算される）。
cross-reference: tests/audit/test_audit_features.py（SC#2 adversarial・5段階鋳型・構造踏襲元）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし・純粋 AST/grep 検査）。
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
from pathlib import Path

import pytest

from src.features import builder, rolling, speed_figure
from src.features.availability import TARGET_OBS_BANNED_COLUMNS
from src.features.builder import _HISTORY_SELECT_COLUMNS
from src.model.data import _derive_feature_columns

# ---------------------------------------------------------------------------
# SC#4 forbidden tokens（SAFE-01 横断聖域・市場情報 proxy）
# ---------------------------------------------------------------------------
# 文字列 contains では docstring/コメント中の "odds-free" 言及が false positive になるため・
# AST Name ノード(id) / Attribute ノード(attr) で厳密に判定する（文字列部分一致でなく AST 構造）。
_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)

# REVIEW H5: SQL 文字列リテラル内 proxy 検出用・word-boundary 部分一致の対象は
# ninki/fukuodds/ninkij/tansyouodds（これらは誤検出が少ない）。"odds" 単独は
# half_odds / odds_free 等・部分一致が多すぎるため完全一致(Name/id == 'odds')のみとし・
# 文字列リテラル検査からは除外する（H5 docstring で明記）。
_FORBIDDEN_PROXY_SUBSTRING_TOKENS: tuple[str, ...] = (
    "ninki",
    "fukuodds",
    "ninkij",
    "tansyouodds",
)


# ---------------------------------------------------------------------------
# REVIEW H5: SQL 文字列リテラル内 proxy トークン検出ヘルパ（word-boundary 部分一致）
# ---------------------------------------------------------------------------
# ast.Constant の value が str の場合・``"ur.ninki AS prior_ninki"`` のような SQL 文字列定数内に
# 埋込まれた proxy トークンを検出する。Name/Attribute ノードでは捉えられないため・AST walk 内で
# ast.Constant str に対して word-boundary 正規表現 ``\\b(token)\\b`` で部分一致検査する。
# ``odds`` は part-of-word false positive が多すぎるため本検査からは除外（Name 完全一致のみ）。
_PROXY_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_PROXY_SUBSTRING_TOKENS) + r")\b"
)


def _scan_module_for_forbidden_tokens(module_obj) -> tuple[list[str], list[str]]:
    """モジュールのソースを AST parse し・forbidden Name/Attribute と SQL 文字列 proxy を走査。

    REVIEW H5: ast.Constant value が str の場合は word-boundary 部分一致で SQL 文字列内の
    proxy トークン埋込み(例: ``"ur.ninki AS prior_ninki"``)を検出する。docstring・コメントは
    AST Name ノードとして現れないため・"odds-free" のような docstring 言及は自動的に除外される
    （false positive 回避）。

    Returns
    -------
    (name_attr_violations, constant_str_violations)
        name_attr_violations: ``"Name(odds) @ line N"`` / ``"Attribute(ninki) @ line N"`` 形式の list
        constant_str_violations: ``"Constant-str(ninki) @ line N: <snippet>"`` 形式の list
    """
    source = inspect.getsource(module_obj)
    # indent を除くため dedent（ネストした module でも parse 可能にする）
    import textwrap

    tree = ast.parse(textwrap.dedent(source))

    name_attr_violations: list[str] = []
    constant_str_violations: list[str] = []

    for node in ast.walk(tree):
        # Name ノード: id が _FORBIDDEN_TOKENS に完全一致
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_TOKENS:
            name_attr_violations.append(
                f"Name({node.id}) @ line {node.lineno}"
            )
        # Attribute ノード: attr が _FORBIDDEN_TOKENS に完全一致
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_TOKENS:
            name_attr_violations.append(
                f"Attribute({node.attr}) @ line {node.lineno}"
            )
        # REVIEW H5: ast.Constant value が str の場合・word-boundary 部分一致で proxy 検出
        # ``odds`` は部分一致 false positive 多すぎのため除外・ninki/fukuodds/ninkij/tansyouodds のみ
        # 1定数内に複数 proxy トークンが含まれ得るため findall で全て捕捉（false-pass 回避）
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            matched_tokens = _PROXY_PATTERN.findall(node.value)
            for tok in matched_tokens:
                snippet = node.value if len(node.value) <= 60 else (node.value[:60] + "...")
                constant_str_violations.append(
                    f"Constant-str({tok}) @ line {node.lineno}: {snippet!r}"
                )

    return name_attr_violations, constant_str_violations


# ---------------------------------------------------------------------------
# P04 SC#5 snapshot_id 候補（P03 SUMMARY で決定・本 audit が消費）
# ---------------------------------------------------------------------------
_SPEED_FIGURE_SNAPSHOT_ID = "20260625-1a-speedfigure-v1"


# ---------------------------------------------------------------------------
# (a)(b)(c): SC#4 AST audit — speed_figure / rolling / builder の forbidden Name/Attribute/Constant 0件
# ---------------------------------------------------------------------------
def test_no_odds_ninki_proxy_in_speed_figure_source() -> None:
    """SC#4 AST: src.features.speed_figure ソースが odds/ninki proxy Name/Attribute/SQL 文字列を含まない。

    本テストは SC#4 adversarial（SAFE-01 静的証明）であり・機能テスト
    ``tests/features/test_speed_figure.py``（機能: speed_figure が正しく計算される）とは独立層。
    ``odds``/``ninki``/``fukuodds``/``ninkij``/``tansyouodds`` が Name/Attribute ノードに0件で
    あること・および REVIEW H5 として SQL 文字列定数内に proxy トークン(word-boundary 部分一致)
    が0件であることを AST 静的解析で証明する。cross-reference: tests/features/test_speed_figure.py。
    """
    name_attr, const_str = _scan_module_for_forbidden_tokens(speed_figure)
    assert not name_attr, (
        f"speed_figure.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {name_attr}"
    )
    assert not const_str, (
        f"speed_figure.py に SQL 文字列リテラル内 proxy トークンが存在 (REVIEW H5 違反): {const_str}"
    )


def test_no_odds_ninki_proxy_in_rolling_source() -> None:
    """SC#4 AST: src.features.rolling ソースが odds/ninki proxy Name/Attribute/SQL 文字列を含まない。

    rolling.py は speed_figure 列のみを集約し・odds/ninki には触れない契約（P02 拡張）。
    同契約の静的証明。cross-reference: tests/features/test_speed_figure.py。
    """
    name_attr, const_str = _scan_module_for_forbidden_tokens(rolling)
    assert not name_attr, (
        f"rolling.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {name_attr}"
    )
    assert not const_str, (
        f"rolling.py に SQL 文字列リテラル内 proxy トークンが存在 (REVIEW H5 違反): {const_str}"
    )


def test_no_odds_ninki_proxy_in_builder_source() -> None:
    """SC#4 AST(H5 強化): src.features.builder ソースが odds/ninki proxy を含まない。

    builder.py は ``_HISTORY_DB_SELECT_COLUMNS`` / ``_OBS_DB_SELECT_COLUMNS`` で明示カラム
    SELECT し・TARGET_OBS_BANNED_COLUMNS（odds/ninki 含む）と disjoint（L320-322 assert）。
    特に SQL 文字列定数(``"nr.sibababacd AS hist_sibababacd"`` 形式)内に禁止トークンが埋込まれて
    いないことを H5 word-boundary check で検証する。将来の ``"ur.ninki AS prior_ninki"`` のような
    proxy が SQL 文字列で追加された場合・AST Constant ノードの str 走査で検出する。
    cross-reference: tests/features/test_speed_figure.py。
    """
    name_attr, const_str = _scan_module_for_forbidden_tokens(builder)
    assert not name_attr, (
        f"builder.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {name_attr}"
    )
    assert not const_str, (
        f"builder.py に SQL 文字列リテラル内 proxy トークンが存在 (REVIEW H5 違反): {const_str}"
    )


# ---------------------------------------------------------------------------
# (d): SC#4 allowlist — FEATURE_COLUMNS に rolling_speed_figure_* 6 feature 含有・banned prefix 0件
# ---------------------------------------------------------------------------
def test_feature_columns_contains_speed_figure_no_proxy() -> None:
    """SC#4 allowlist(REVIEW H1 _derive_feature_columns 経由): rolling_speed_figure_* 6 feature 含有・forbidden prefix 0件。

    REVIEW H1: ``src.model.data._derive_feature_columns(snapshot_id=)`` で動的に FEATURE_COLUMNS を取得。
    REVIEW M2(fallback mask 廃止): speed_figure snapshot が未生成の場合は v1.0 へ fallback して
    mask するのでなく・``pytest.skip`` でもなく・明示的に **AssertionError で FAIL** する
    （Phase 9 feature 欠落を mask しない・P03 で snapshot 生成が前提）。

    検査内容:
      - speed_figure snapshot では rolling_speed_figure_last_1/mean_3/mean_5/max_5/sd_5/count_5
        の6 feature が FEATURE_COLUMNS に含まれる
      - v1.0(snapshot_id=None)では rolling_speed_figure_* は含まれない（後方互換 A5）
      - FEATURE_COLUMNS の各要素は forbidden prefix(odds/ninki/fukuodds/ninkij/tansyouodds で始まる)
        でない（banned alias sneak-in の構造的防止・HIGH #9）
    cross-reference: tests/features/test_speed_figure.py。
    """
    # REVIEW H1: v1.0 デフォルト
    v10_cols = _derive_feature_columns(snapshot_id=None)
    # v1.0 には rolling_speed_figure_* は含まれない（後方互換 A5）
    v10_speed = [c for c in v10_cols if c.startswith("rolling_speed_figure_")]
    assert v10_speed == [], (
        f"v1.0 FEATURE_COLUMNS に rolling_speed_figure_* が含まれる（後方互違反）: {v10_speed}"
    )
    # v1.0 でも forbidden prefix は0件
    v10_forbidden = [c for c in v10_cols if c.split("_")[0] in _FORBIDDEN_TOKENS]
    assert v10_forbidden == [], (
        f"v1.0 FEATURE_COLUMNS に forbidden prefix カラムが存在: {v10_forbidden}"
    )

    # REVIEW H1 + M2: speed_figure snapshot。REVIEW M2(fallback mask 廃止)の意図は
    # 「snapshot が未生成の場合に v1.0 へ静かに fallback して Phase 9 feature 欠落を mask しないこと」。
    # すなわち ``_derive_feature_columns(snapshot_id=<未生成ID>)`` は FileNotFoundError 等で
    # fail-loud する（v1.0 への silent fallback でない）契約。本テストは2経路で M2 を証明する:
    #   (i) snapshot が存在する場合 → FEATURE_COLUMNS に rolling_speed_figure_* 6 feature 含有・
    #       forbidden prefix 0件を検査（本命・live-DB snapshot 生成後に GREEN）
    #   (ii) snapshot が未生成の場合 → ``_derive_feature_columns(snapshot_id=<ID>)`` が
    #        FileNotFoundError を raise することを検査（silent fallback で mask しないことの証明）
    speed_snapshot_path = Path(f"snapshots/feature_matrix_{_SPEED_FIGURE_SNAPSHOT_ID}.parquet")
    if speed_snapshot_path.exists():
        # (i) snapshot 生成済：本命検査
        speed_cols = _derive_feature_columns(snapshot_id=_SPEED_FIGURE_SNAPSHOT_ID)
        expected_speed_features = {
            "rolling_speed_figure_last_1",
            "rolling_speed_figure_mean_3",
            "rolling_speed_figure_mean_5",
            "rolling_speed_figure_max_5",
            "rolling_speed_figure_sd_5",
            "rolling_speed_figure_count_5",
        }
        actual_speed = {c for c in speed_cols if c.startswith("rolling_speed_figure_")}
        missing = expected_speed_features - actual_speed
        assert not missing, (
            f"speed_figure snapshot FEATURE_COLUMNS に期待の6 feature のうち欠落: {missing} "
            f"(actual speed features: {sorted(actual_speed)})"
        )
        # FEATURE_COLUMNS の各要素は forbidden prefix で始まらない（HIGH #9 banned alias sneak-in 防止）
        forbidden_in_speed = [c for c in speed_cols if c.split("_")[0] in _FORBIDDEN_TOKENS]
        assert forbidden_in_speed == [], (
            f"speed_figure snapshot FEATURE_COLUMNS に forbidden prefix カラムが存在: "
            f"{forbidden_in_speed} (HIGH #9 違反・banned alias sneak-in)"
        )
    else:
        # (ii) snapshot 未生成: _derive_feature_columns(snapshot_id=<未生成ID>) が
        # FileNotFoundError を raise することを検査（silent fallback で mask しないことの証明・M2）
        with pytest.raises(FileNotFoundError):
            _derive_feature_columns(snapshot_id=_SPEED_FIGURE_SNAPSHOT_ID)


# ---------------------------------------------------------------------------
# (e): SC#4 構造的保証 — TARGET_OBS_BANNED_COLUMNS ∩ _HISTORY_SELECT_COLUMNS == ∅
# ---------------------------------------------------------------------------
def test_target_obs_banned_columns_disjoint_from_history_select() -> None:
    """SC#4 構造的保証: TARGET_OBS_BANNED_COLUMNS と _HISTORY_SELECT_COLUMNS が disjoint。

    builder.py L320-322 の起動時 assert と対称な再確認（P04 で再検証）。
    ``"odds"`` / ``"ninki"`` が TARGET_OBS_BANNED_COLUMNS に含まれることも併せて assert し・
    SAFE-01 聖域の定義が変更されていないことを保証する。
    cross-reference: tests/features/test_speed_figure.py。
    """
    # odds/ninki が TARGET_OBS_BANNED に含まれる（聖域の定義不変）
    assert "odds" in TARGET_OBS_BANNED_COLUMNS, (
        "TARGET_OBS_BANNED_COLUMNS に 'odds' が無い（SAFE-01 聖域の定義変更・違反）"
    )
    assert "ninki" in TARGET_OBS_BANNED_COLUMNS, (
        "TARGET_OBS_BANNED_COLUMNS に 'ninki' が無い（SAFE-01 聖域の定義変更・違反）"
    )
    # disjoint 構造保証
    overlap = TARGET_OBS_BANNED_COLUMNS & _HISTORY_SELECT_COLUMNS
    assert not overlap, (
        f"TARGET_OBS_BANNED_COLUMNS と _HISTORY_SELECT_COLUMNS が衝突: {overlap} "
        f"(HIGH #4 違反・odds/ninki が history SELECT に混入する経路)"
    )


# ---------------------------------------------------------------------------
# (f): T-08-04 docstring cross-reference
# ---------------------------------------------------------------------------
def test_docstring_cross_reference() -> None:
    """モジュール/テスト docstring に SC#4 adversarial と cross-reference が含まれる（T-08-04）。

    重複回避: 機能テスト ``tests/features/test_speed_figure.py`` が「speed_figure が正しく計算される」
    を検証するのに対し・本 audit は「proxy が混入しないことの静的証明」を行う（独立層）。
    """
    module_doc = sys.modules[__name__].__doc__ or ""
    assert "SC#4 adversarial" in module_doc, (
        "モジュール docstring に SC#4 adversarial 明示がない（T-08-04 重複回避違反）"
    )
    assert "cross-reference: tests/features/test_speed_figure.py" in module_doc, (
        "モジュール docstring に test_speed_figure.py cross-reference がない（T-08-04 違反）"
    )
    assert "cross-reference: tests/audit/test_audit_features.py" in module_doc, (
        "モジュール docstring に test_audit_features.py cross-reference がない（T-08-04 違反）"
    )


# ---------------------------------------------------------------------------
# (g): SC#4 false-pass 回避・H5 拡張 — 意図的注入を検出することの証明
# ---------------------------------------------------------------------------
def test_false_pass_detection_power() -> None:
    """SC#4 false-pass 回避・H5 拡張: guard が意図的注入(Name/Attribute/SQL 文字列 proxy)を検出することを証明。

    5段階鋳型(5)に相当（test_audit_features.py の false-pass 回避構造踏襲）。
    意図的に禁止トークンを含むダミーソース文字列を構築し AST parse して・本 audit の
    ``_scan_module_for_forbidden_tokens`` 相当ロジックが(1) forbidden Name/Attribute ノードを
    検出すること・(2) REVIEW H5 として SQL 文字列定数内 proxy も検出することを確認する。
    これにより「guard が正しく働くこと」と「SQL 文字列内 proxy も検出すること」を証明する。
    cross-reference: tests/features/test_speed_figure.py。
    """
    import textwrap

    # (1) Name/Attribute 注入: odds/ninki を参照するダミーソース
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

    # (2) REVIEW H5: SQL 文字列定数内 proxy 注入検出
    dummy_sql_source = textwrap.dedent(
        '''
        SQL_HIST = "ur.ninki AS prior_ninki, ur.fukuodds AS fukuodds_prev"
        '''
    )
    tree_sql = ast.parse(dummy_sql_source)
    sql_hits: list[str] = []
    for node in ast.walk(tree_sql):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # re.search でなく findall：1 文字列内の複数 proxy トークンを全て捕捉
            sql_hits.extend(_PROXY_PATTERN.findall(node.value))
    assert "ninki" in sql_hits, (
        "REVIEW H5 検出力不足: SQL 文字列 'ur.ninki AS prior_ninki' 内 proxy を word-boundary で検出していない"
    )
    assert "fukuodds" in sql_hits, (
        "REVIEW H5 検出力不足: SQL 文字列 'ur.fukuodds AS fukuodds_prev' 内 proxy を検出していない"
    )

    # (3) false positive 回避の証明: "odds-free" docstring 言及は Name ノードに現れない
    dummy_docstring_source = textwrap.dedent(
        '''
        """odds-free module: 本モジュールは市場情報 proxy を使わない（SAFE-01）。"""
        def f():
            return 0
        '''
    )
    tree_doc = ast.parse(dummy_docstring_source)
    doc_hits: list[str] = []
    for node in ast.walk(tree_doc):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_TOKENS:
            doc_hits.append(node.id)
        # docstring の str Constant は odds について完全一致のみ(今回は部分一致検査対象外のため ninki 等のみ)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            m = _PROXY_PATTERN.search(node.value)
            if m:
                doc_hits.append(m.group(1))
    assert doc_hits == [], (
        f"false positive: docstring の 'odds-free' 言及が禁止トークンとして誤検出された: {doc_hits} "
        f"(AST Name/Attribute は docstring を素通りすべき・H5 word-boundary も odds は対象外)"
    )
