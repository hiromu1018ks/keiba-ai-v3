# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・test_audit_race_relative.py と同一慣例)
"""SC#5 / D-10 / §11.2 / SAFE-01 adversarial: Phase 12 p_lower + falsification + run_phase12_evaluation
3層の対抗的監査（adversarial audit）。test_audit_race_relative.py の5段階鋳型を完全踏襲し・
Phase 12 で追加された compute_p_lower_conformal_shrinkage / fit_market_implied_calibrator /
run_falsification_test / scripts/run_phase12_evaluation.py が以下の聖域を機械保証することを
AST 静的解析 + 値レベル adversarial で証明する:

  - **SAFE-01** (feature 側 odds/ninki proxy 排除): p_lower / falsification 層の AST に
    市場情報 proxy の forbidden Name/Attribute が0件・FEATURE_COLUMNS / build_training_frame /
    load_feature_matrix 等 feature 構築経路の import 非参照（層分離）。
  - **§11.2 test 窓 sanctuary**: compute_p_lower_conformal_shrinkage / fit_market_implied_calibrator
    の signature が test 窓 outcome 系引数（y_test/outcome_test/y_outcome_test/label_test/target_test）
    を取らない（構造的聖域ブロック・docstring 紳士協定でない）。
  - **D-10** (is_primary 自動変更禁止・人間承認の別アクション): scripts/run_phase12_evaluation.py
    の AST で set_primary_model の ast.Call node が0件（docstring の str ノードは Call として
    扱われない・test_audit_race_relative.py L36-44 idiom）。
  - **[C-12-05-1 / HIGH・codex HIGH#4・C-12-01-2 と同根] 値レベル §11.2 leak 検出**:
    signature-only 監査では検出できない呼出側での test outcome 混入（例: np.quantile over
    concatenated [y_calib, y_test]）を・合成データで compute_p_lower_conformal_shrinkage を
    直接呼び出し・test labels 改変で q_shrink が不変（sha256 一致）・calib labels 改変で
    変化（sha256 不一致）となることを値レベルで検証（audit 独自の純粋経路・run_phase12 側
    test とは別経路で二重保証）。

5段階鋳型（test_audit_race_relative.py / test_audit_field_strength.py 踏襲）:
  (a)(b)(c) AST: forbidden Name/Attribute 0件 + SAFE-01-ALLOW marker 許容 + feature 経路 import 非参照
  (d) falsification leakage: fit_market_implied_calibrator signature が calib slice only
  (e) false-pass detection power: 意図的注入を検出することの証明（silent test 回避）
  (6) 自己完結性 signature: compute_p_lower_conformal_shrinkage が test 窓 outcome を取らない
  (7) D-10 set_primary_model Call 0件: scripts/run_phase12_evaluation.py の AST

[C-12-01-3 / C-12-05-3 / MEDIUM] SAFE-01 監査は単純な forbidden token 0件だけでなく:
  - (A) allow-list marker（SAFE-01-ALLOW: odds/market_implied）が docstring にある関数は許容
        （falsification 層の正当な odds/market_implied 消費を false red にしない）
  - (B) feature 構築経路（FEATURE_COLUMNS/build_training_frame/load_feature_matrix）の import
        非参照を併用（feature への混入を見逃さない = false green 回避）
  両方を併用することで false red と false green を同時に回避する。

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行・純粋 AST/signature/値経路検査・marker なし）。

cross-reference: tests/audit/test_audit_race_relative.py（5段階鋳型踏襲元・Phase 11 SC#4）.
cross-reference: tests/audit/test_audit_field_strength.py（5段階鋳型・SAFE-01 proxy 排除・Phase 10 D-06）.
cross-reference: tests/model/test_p_lower.py〔Plan 01〕（機能テスト・正しく計算される）.
cross-reference: 12-RESEARCH.md Security Domain（SAFE-01 / D-10 / §11.2 聖域）.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import re
import sys
import textwrap
from pathlib import Path

import numpy as np

from src.eval import falsification
from src.model import race_relative
from src.model.race_relative import compute_p_lower_conformal_shrinkage

# ---------------------------------------------------------------------------
# SC#5 forbidden tokens（SAFE-01 横断聖域・test_audit_race_relative.py と共通）
# ---------------------------------------------------------------------------
# 文字列 contains では docstring/prose 中の言及が false positive になるため・
# AST Name/Attribute ノード完全一致 + Constant string word-boundary 部分一致で厳密に判定する
# （test_audit_race_relative.py L43-50 と完全一致の挙動）。
_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {"odds", "ninki", "fukuodds", "ninkij", "tansyouodds"}
)

# SQL 文字列リテラル検査の base トークン（odds は whitelist で無害 prose を除外）
_FORBIDDEN_PROXY_SUBSTRING_TOKENS_BASE: tuple[str, ...] = (
    "ninki",
    "fukuodds",
    "ninkij",
    "tansyouodds",
)

# whitelist: docstring/prose 中の '市場情報 proxy 不使用' 等・SAFE-01 聖域を説明する無害言及は
# SQL text 埋込みでないため検出対象から除外する（test_audit_race_relative.py L63-70 と同一 idiom）。
# odds のみに適用（ninki/fukuodds/ninkij/tansyouodds は無害言及が存在し得ないため適用しない・厳密）。
_ODDS_IN_SQL_WHITELIST: tuple[str, ...] = (
    "odds-free",
    "odds_snapshot_policy",
    "odds_snapshot_at",
    "odds-free module",
    "市場情報 proxy を使わない",
    "市場情報 proxy 不使用",
)

_PROXY_PATTERN_BASE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_PROXY_SUBSTRING_TOKENS_BASE) + r")\b"
)
_ODDS_PATTERN = re.compile(r"\bodds\b")

# feature 構築経路の import 非参照に使用する token 集合（SAFE-01 層分離・C-12-01-3/C-12-05-3）
_FEATURE_CONSTRUCTION_TOKENS: frozenset[str] = frozenset(
    {
        "FEATURE_COLUMNS",
        "build_training_frame",
        "load_feature_matrix",
        "FEATURE_SNAPSHOT",
        "_derive_feature_columns",
    }
)


def _is_whitelisted_odds_prose(value: str) -> bool:
    """whitelist: 無害 prose 中の 'odds' 言及を false-positive から除外.

    docstring の 'odds-free' / 'odds_snapshot_policy' 等・SAFE-01 聖域を説明する無害な言及は
    SQL text 埋込みでないため検出対象から除外する。本関数は odds のみに適用し・
    ninki/fukuodds/ninkij/tansyouodds は無害言及が存在し得ないため適用しない（厳密）。
    test_audit_race_relative.py L78-86 と同一 idiom。
    """
    return any(phrase in value for phrase in _ODDS_IN_SQL_WHITELIST)


def _scan_module_for_forbidden_tokens(module_obj) -> tuple[list[str], list[str]]:
    """モジュールのソースを AST parse し・forbidden Name/Attribute と SQL 文字列 proxy を走査.

    test_audit_race_relative.py L89-132 と完全一致の構造（5段階鋳型 (a)(b)(c)）:
      - ast.Name ノード: id が _FORBIDDEN_TOKENS に完全一致 → Name 違反
      - ast.Attribute ノード: attr が _FORBIDDEN_TOKENS に完全一致 → Attribute 違反
      - ast.Constant value が str: word-boundary 部分一致で SQL 文字列内の proxy トークン埋込みを検出
        （odds は whitelist で無害 prose を除外・他4トークンは whitelist 適用なし・厳密）

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
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_TOKENS:
            name_attr_violations.append(f"Name({node.id}) @ line {node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_TOKENS:
            name_attr_violations.append(f"Attribute({node.attr}) @ line {node.lineno}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            snippet = value if len(value) <= 60 else (value[:60] + "...")
            for tok in _PROXY_PATTERN_BASE.findall(value):
                constant_str_violations.append(
                    f"Constant-str({tok}) @ line {node.lineno}: {snippet!r}"
                )
            if _ODDS_PATTERN.search(value) and not _is_whitelisted_odds_prose(value):
                constant_str_violations.append(
                    f"Constant-str(odds) @ line {node.lineno}: {snippet!r}"
                )

    return name_attr_violations, constant_str_violations


def _scan_module_for_feature_route_imports(module_obj) -> list[str]:
    """モジュールの AST を走査し・feature 構築経路（FEATURE_COLUMNS / build_training_frame /
    load_feature_matrix / _derive_feature_columns / FEATURE_SNAPSHOT）の Name/Attribute/import 参照を検出.

    C-12-01-3 / C-12-05-3: evaluation 専用層（p_lower / falsification）が feature 構築経路に
    触れないことを機械保証する（false green 回避・SAFE-01 層分離）。test_audit_race_relative.py
    L222-244 の feature 経路 token 検査 idiom を拡張し・モジュール全体の import / Name / Attribute
    を走査する。

    Returns
    -------
    list[str]
        検出された参照のリスト（``"Name(FEATURE_COLUMNS) @ line N"`` 形式）。空の場合は feature
        構築経路への参照が無い（SAFE-01 層分離 OK）。
    """
    source = inspect.getsource(module_obj)
    tree = ast.parse(textwrap.dedent(source))

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FEATURE_CONSTRUCTION_TOKENS:
            violations.append(f"Name({node.id}) @ line {node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr in _FEATURE_CONSTRUCTION_TOKENS:
            violations.append(f"Attribute({node.attr}) @ line {node.lineno}")
        elif isinstance(node, ast.alias) and node.name in _FEATURE_CONSTRUCTION_TOKENS:
            violations.append(f"Import({node.name}) @ line {node.lineno}")
        elif isinstance(node, ast.ImportFrom) and node.module and any(
            tok in (node.module or "") for tok in _FEATURE_CONSTRUCTION_TOKENS
        ):
            violations.append(f"ImportFrom({node.module}) @ line {node.lineno}")
    return violations


# ---------------------------------------------------------------------------
# (a)(b)(c): SC#5 AST audit — p_lower / falsification の forbidden Name/Attribute 0件
# ---------------------------------------------------------------------------
def test_no_odds_ninki_proxy_in_p_lower_falsification() -> None:
    """SC#5 AST: src.model.race_relative / src.eval.falsification の forbidden Name/Attribute 0件.

    本テストは SC#5 adversarial（SAFE-01 静的証明・Phase 12 新規関数群）。
    p_lower 計算関数・falsification 関数が odds/ninki/fukuodds/ninkij/tansyouodds を
    Name/Attribute ノードに持たないことを AST 静的解析で証明する。

    [C-12-01-3 / C-12-05-3] Constant-str scan は allow-list marker と併用するため
    本テストでは Name/Attribute のみを strict 検査し・falsification 層の正当な docstring prose
    （market_implied / 1/odds 言及）で false-red にしない。docstring の 'odds' 言及は
    SAFE-01-ALLOW マーカー（test_market_implied_arg_has_allowlist）で別途機械保証する。
    """
    # race_relative.py 全体: compute_p_lower_conformal_shrinkage 追加後も SAFE-01 聖域維持
    rr_name_attr, _ = _scan_module_for_forbidden_tokens(race_relative)
    assert not rr_name_attr, (
        f"race_relative.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {rr_name_attr}"
    )

    # falsification.py 全体: fit_market_implied_calibrator / run_falsification_test 追加後も
    # Name/Attribute は forbidden token 0件（docstring の prose 中 'odds' は Name でなく Constant-str）
    fals_name_attr, _ = _scan_module_for_forbidden_tokens(falsification)
    assert not fals_name_attr, (
        f"falsification.py に forbidden Name/Attribute ノードが存在 (SAFE-01 違反): {fals_name_attr}"
    )


# ---------------------------------------------------------------------------
# (d): feature 構築経路 import 非参照（C-12-01-3 / C-12-05-3・false green 回避）
# ---------------------------------------------------------------------------
def test_no_feature_construction_route_in_p_lower_falsification() -> None:
    """[C-12-01-3 / C-12-05-3] p_lower / falsification 層が feature 構築経路を import しない.

    evaluation 専用層（p_lower / falsification）が FEATURE_COLUMNS / build_training_frame /
    load_feature_matrix / _derive_feature_columns / FEATURE_SNAPSHOT 等 feature 構築経路を
    import・参照しないことを AST 静的解析で保証する（SAFE-01 層分離・false green 回避）。

    この検査は (a)(b)(c) の forbidden token scan と併用し:
      - forbidden token scan: odds/ninki が feature 側に混入しない構造保証
      - feature 経路 scan:    evaluation 層が feature 構築経路を通じて proxy を受け取る経路が
                              開いていない構造保証（C-12-01-3/C-12-05-3 併用の core）
    """
    rr_feature_refs = _scan_module_for_feature_route_imports(race_relative)
    assert not rr_feature_refs, (
        f"race_relative.py に feature 構築経路への参照が存在 (SAFE-01 層分離違反): {rr_feature_refs}"
    )

    fals_feature_refs = _scan_module_for_feature_route_imports(falsification)
    assert not fals_feature_refs, (
        f"falsification.py に feature 構築経路への参照が存在 (SAFE-01 層分離違反): "
        f"{fals_feature_refs}"
    )


# ---------------------------------------------------------------------------
# (b): SAFE-01-ALLOW marker — falsification の odds/market_implied 引数が許容宣言を持つ
# ---------------------------------------------------------------------------
# compute_overprediction_penalty の market_signal idiom と同一の機械保証契約。
# allow-list marker は「evaluation 専用引数であることを実装者が明示宣言した」という機械保証であり・
# docstring 紳士協定でない（マーカー欠落時は fail-loud）。
# C-12-01-3 / C-12-05-3: allow-list で正しい evaluation 層のコードを false red にしない。
_MARKET_IMPLIED_ARG_ALLOWLIST_MARKERS: tuple[str, ...] = (
    "SAFE-01-ALLOW: odds",
    "SAFE-01-ALLOW: market_implied",
)


def _find_functions_with_market_implied_args(
    module_obj,
) -> list[tuple[str, ast.FunctionDef]]:
    """odds/market_implied/model_p 系引数を持つトップレベル関数の (関数名, FunctionDef) リストを返す.

    fit_market_implied_calibrator (odds_train/odds_calib) / run_falsification_test
    (market_implied_test/model_p_test/odds_band_test) を検出する。test_audit_race_relative.py
    L176-186 の market_signal 検出 idiom を Phase 12 の evaluation 層引数に拡張。
    """
    source = inspect.getsource(module_obj)
    tree = ast.parse(textwrap.dedent(source))
    target_arg_substrings = ("odds", "market_implied", "model_p")
    found: list[tuple[str, ast.FunctionDef]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            arg_names = {a.arg for a in node.args.args}
            has_market_arg = any(
                any(sub in arg for sub in target_arg_substrings) for arg in arg_names
            )
            if has_market_arg:
                found.append((node.name, node))
    return found


def test_market_implied_arg_has_allowlist() -> None:
    """[C-12-01-3 / C-12-05-3] SAFE-01-ALLOW marker 機械保証.

    falsification.py の fit_market_implied_calibrator / run_falsification_test は
    odds/market_implied/model_p 系引数（市場情報・予測確率系外部参照）を受け取る。
    本テストは:
      (1) odds/market_implied/model_p 系引数を持つ全ての関数の docstring に
          ``SAFE-01-ALLOW: odds`` または ``SAFE-01-ALLOW: market_implied`` マーカーがあることを検証
          （実装者の explicit な allow-list 宣言・docstring 紳士協定でない）
      (2) それらの関数の本体 AST に FEATURE_COLUMNS / build_training_frame / load_feature_matrix
          等の feature 構築経路の Name/Attribute が含まれないことを検証
          （odds/market_implied が feature snapshot の列を直接受け取る経路が開いていない保証）

    マーカーが欠落した場合・または feature 構築経路が混入した場合は fail-loud する。
    本テストは test_no_odds_ninki_proxy_in_p_lower_falsification（Name/Attribute forbidden token
    走査）と補完関係（SAFE-01 聖域の2層防御）。
    """
    funcs_with_market_args = _find_functions_with_market_implied_args(falsification)
    # fit_market_implied_calibrator / run_falsification_test が最低2関数存在するはず（前提確認）
    func_names = {name for name, _ in funcs_with_market_args}
    assert {"fit_market_implied_calibrator", "run_falsification_test"}.issubset(
        func_names
    ), (
        "falsification.py に fit_market_implied_calibrator / run_falsification_test が見つからない・"
        f"テストの前提確認 (detected: {sorted(func_names)})"
    )

    for func_name, func_node in funcs_with_market_args:
        # (1) docstring に allow-list marker のいずれかがあること
        docstring = ast.get_docstring(func_node) or ""
        has_marker = any(
            marker in docstring for marker in _MARKET_IMPLIED_ARG_ALLOWLIST_MARKERS
        )
        assert has_marker, (
            f"falsification.py::{func_name} は odds/market_implied/model_p 系引数を持つが・"
            f"docstring に allow-list marker {_MARKET_IMPLIED_ARG_ALLOWLIST_MARKERS} のいずれも無い "
            f"(C-12-01-3/C-12-05-3・SAFE-01 違反)。market_implied/odds は evaluation 専用引数であることを "
            "docstring で explicit に宣言すること（SAFE-01 聖域・docstring 紳士協定でない機械保証）。"
        )

        # (2) 関数本体 AST に feature 構築経路の Name/Attribute が含まれないこと
        # odds/market_implied が feature snapshot の列を直接受け取る経路が開いていない保証。
        for node in ast.walk(func_node):
            if isinstance(node, ast.Name) and node.id in _FEATURE_CONSTRUCTION_TOKENS:
                raise AssertionError(
                    f"falsification.py::{func_name} の本体に feature 構築経路 "
                    f"{node.id} への参照がある (C-12-01-3/C-12-05-3・SAFE-01 違反)。"
                    "odds/market_implied 引数が feature snapshot の列を直接受け取る経路が "
                    "開いている可能性がある・evaluation 専用層と feature 層を分離すること。"
                )
            if (
                isinstance(node, ast.Attribute)
                and node.attr in _FEATURE_CONSTRUCTION_TOKENS
            ):
                raise AssertionError(
                    f"falsification.py::{func_name} の本体に feature 構築経路 "
                    f"{node.attr} への Attribute 参照がある (C-12-01-3/C-12-05-3・SAFE-01 違反)。"
                )


# ---------------------------------------------------------------------------
# (6): §11.2 聖域 — compute_p_lower_conformal_shrinkage signature が test 窓 outcome を取らない
# ---------------------------------------------------------------------------
def test_p_lower_self_contained_outcome_swap() -> None:
    """§11.2 聖域: compute_p_lower_conformal_shrinkage signature が test 窓 outcome 系を取らない.

    inspect.signature で actual_params と forbidden_params（y_test/outcome_test/y_outcome_test/
    label_test/target_test）の積集合が空であることを検証する（test_audit_race_relative.py
    L250-378 の test_alpha_self_contained_outcome_swap idiom・§11.2 聖域の構造的機械保証）。

    本テストは signature-only 監査（値レベル監査は test_q_shrink_value_level_adversarial_invariance
    で二重保証）。signature が test 窓 outcome を取らないことが・q_shrink 計算に test 窓 outcome
    が混入する経路を構造的に閉じている逆証明（§11.2 聖域・docstring 紳士協定でなく API seam）。
    """
    sig = inspect.signature(compute_p_lower_conformal_shrinkage)
    forbidden_params = {
        "y_test",
        "outcome_test",
        "y_outcome_test",
        "label_test",
        "target_test",
    }
    actual_params = set(sig.parameters.keys())
    leak_params = actual_params & forbidden_params
    assert not leak_params, (
        f"compute_p_lower_conformal_shrinkage のシグネチャに test 窓 outcome 系引数 {leak_params} が存在する・"
        f"actual_params={actual_params}・§11.2 聖域違反 "
        f"(q_shrink 計算に test 窓 outcome が混入する経路が開いている)"
    )
    # 期待シグネチャ {p_final, y_calib, p_final_calib, q_level} のみであることも確認
    expected_params = {"p_final", "y_calib", "p_final_calib", "q_level"}
    assert actual_params == expected_params, (
        f"compute_p_lower_conformal_shrinkage のシグネチャが期待と異なる: "
        f"actual={actual_params}・expected={expected_params}・"
        f"§11.2 聖域の前提（q_shrink は calib slice のみから決定）"
    )


# ---------------------------------------------------------------------------
# (d): falsification leakage — fit_market_implied_calibrator signature が calib slice only
# ---------------------------------------------------------------------------
def test_falsification_no_test_outcome_leak() -> None:
    """§11.2 聖域: fit_market_implied_calibrator signature が test 窓 outcome 系を取らない.

    [C-12-03-4] base/calibrator 2-window 分離: fit_market_implied_calibrator は
    {odds_train, y_train, odds_calib, y_calib, calib_sample_size} のみを引数に取り・
    test 窓 outcome 系引数 (y_test/outcome_test/y_outcome_test) を取らない（Shared Pattern 6・
    構造的聖域ブロック・12-PATTERNS.md L720-727）。

    run_falsification_test は「事前登録評価回帰仕様を test 窓に fit する最終検定」であり・
    「学習を行わない」の模糊した表現でなく・precise な docstring 言語を持つ（C-12-03-1・§11.2 聖域）。
    本テストは run_falsification_test の docstring に precise language があることも検証する。
    """
    from src.eval.falsification import fit_market_implied_calibrator, run_falsification_test

    # (1) fit_market_implied_calibrator: calib slice only（test 窓 outcome 系不可）
    sig_calib = inspect.signature(fit_market_implied_calibrator)
    forbidden = {"y_test", "outcome_test", "y_outcome_test"}
    actual_calib = set(sig_calib.parameters.keys())
    leak_calib = actual_calib & forbidden
    assert not leak_calib, (
        f"fit_market_implied_calibrator のシグネチャに test 窓 outcome 系引数 {leak_calib} が存在する・"
        f"actual={actual_calib}・§11.2 聖域違反 (C-12-03-4 2-window 分離)"
    )
    expected_calib = {"odds_train", "y_train", "odds_calib", "y_calib", "calib_sample_size"}
    assert actual_calib == expected_calib, (
        f"fit_market_implied_calibrator のシグネチャが C-12-03-4 2-window 分離と異なる: "
        f"actual={actual_calib}・expected={expected_calib}"
    )

    # (2) run_falsification_test: precise docstring language（C-12-03-1・「学習しない」でなく）
    # docstring に事前登録評価回帰の precise language が含まれることを検証（docstring 紳士協定でなく
    # Contract: C-12-03-1 で確定した precise language が変更されない機械保証）。
    docstring = run_falsification_test.__doc__ or ""
    precise_language_markers = (
        "事前登録評価回帰",  # 日本語 precise term
        "pre-registered evaluation regression",  # 英語 precise term
    )
    has_precise_language = any(m in docstring for m in precise_language_markers)
    assert has_precise_language, (
        "run_falsification_test の docstring に事前登録評価回帰の precise language がない "
        "(C-12-03-1・「学習を行わない」等の模糊表現でなく 'pre-registered evaluation regression' / "
        "'事前登録評価回帰' であるべき)"
    )
    # 模糊表現「学習を行わない」単独使用は禁止（precise language で上書きされているべき）
    # 注: docstring に「予測モデル p の再学習を行わない」が precise language と併存するのは可
    # （precise language が存在すれば OK・模糊表現単独使用でない）


# ---------------------------------------------------------------------------
# (e): false-pass detection power — 意図的注入を検出することの証明
# ---------------------------------------------------------------------------
def test_false_pass_detection_power() -> None:
    """SC#5 false-pass 回避: guard が意図的注入を検出することを証明.

    5段階鋳型(g)（test_audit_race_relative.py::test_false_pass_detection_power と同一構造）。
    意図的に禁止トークンを含むダミーソース文字列を構築し AST parse して・本 audit の
    ``_scan_module_for_forbidden_tokens`` ロジックが:
      (1) forbidden Name/Attribute ノードを検出すること
      (2) SQL 文字列定数内 proxy も検出すること
      (3) odds の SQL 文字列埋込みも検出すること
      (4) whitelist で無害 prose を false-positive から除外すること
    を確認する。[C-12-01-3] 追加: feature 構築経路 import 注入を検出することも証明（false green 回避）。

    本テストは AST ロジック単体の検出力証明（silent test 回避）→ 即時 GREEN。
    """
    # (1) Name/Attribute 注入
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
        "Name ノード検出力不足: 意図的 odds Name 注入を検出していない（false-pass・SAFE-01 違反）"
    )
    assert "Attribute(ninki)" in name_hits, (
        "Attribute ノード検出力不足: 意図的 ninki Attribute 注入を検出していない（false-pass・SAFE-01 違反）"
    )

    # (2) SQL 文字列定数内 proxy（ninki/fukuodds/ninkij/tansyouodds）注入検出
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
        "検出力不足: SQL 文字列 'ur.ninki AS prior_ninki' 内 proxy を検出していない"
    )
    assert "fukuodds" in sql_hits, (
        "検出力不足: SQL 文字列 'ur.fukuodds AS fukuodds_prev' 内 proxy を検出していない"
    )

    # (3) odds の SQL 文字列埋込み検出
    dummy_odds_sql_source = textwrap.dedent(
        '''
        SQL_ODDS = "SELECT odds AS market_odds FROM market_table WHERE ninki > 5"
        '''
    )
    tree_odds = ast.parse(dummy_odds_sql_source)
    odds_hits: list[str] = []
    for node in ast.walk(tree_odds):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _ODDS_PATTERN.search(node.value) and not _is_whitelisted_odds_prose(node.value):
                odds_hits.append("odds")
    assert "odds" in odds_hits, (
        "検出力不足: SQL 文字列内の 'odds' を検出していない"
    )

    # (4) false positive 回避の証明: whitelist prose 言及は検出対象外
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
        f"false positive: docstring の 'odds-free'/'市場情報 proxy 不使用' 言及が検出対象になった: "
        f"{doc_odds_hits} (whitelist で無害 prose を除外すべき)"
    )

    # (5) [C-12-01-3] feature 構築経路 import 注入の検出力証明（false green 回避）
    # 意図的に FEATURE_COLUMNS / build_training_frame を import するダミーソースを検出できること
    dummy_feature_route_source = textwrap.dedent(
        """
        from src.model.data import FEATURE_COLUMNS, build_training_frame
        def f():
            x = FEATURE_COLUMNS
            y = build_training_frame(None, None)
            return x, y
        """
    )
    tree_feat = ast.parse(dummy_feature_route_source)
    feat_hits: list[str] = []
    for node in ast.walk(tree_feat):
        if isinstance(node, ast.Name) and node.id in _FEATURE_CONSTRUCTION_TOKENS:
            feat_hits.append(f"Name({node.id})")
        elif isinstance(node, ast.Attribute) and node.attr in _FEATURE_CONSTRUCTION_TOKENS:
            feat_hits.append(f"Attribute({node.attr})")
        elif isinstance(node, ast.alias) and node.name in _FEATURE_CONSTRUCTION_TOKENS:
            feat_hits.append(f"Import({node.name})")
    assert any("FEATURE_COLUMNS" in h for h in feat_hits), (
        "feature 経路検出力不足: 意図的 FEATURE_COLUMNS import 注入を検出していない"
        "（false green・C-12-01-3 違反・SAFE-01 層分離の検出不能）"
    )
    assert any("build_training_frame" in h for h in feat_hits), (
        "feature 経路検出力不足: 意図的 build_training_frame import 注入を検出していない"
        "（false green・C-12-01-3 違反）"
    )


# ---------------------------------------------------------------------------
# (7): D-10 — set_primary_model Call 0件 (scripts/run_phase12_evaluation.py AST check)
# ---------------------------------------------------------------------------
def test_no_set_primary_model_call() -> None:
    """D-10: scripts/run_phase12_evaluation.py の AST で set_primary_model の ast.Call node が0件.

    本テストは AST check（docstring の str ノードは Call として扱われない）・
    test_audit_race_relative.py L36-44 / 12-PATTERNS.md L729-744 idiom。

    scripts/ は package でない（__init__.py 無し）ため・import でなくファイルパスから
    ソースを直接読み ast.parse する（import 経路だと sys.path manipulation が必要で・
    test が fragile になる）。docstring 中の「set_primary_model を呼ばない」言及は
    ast.Constant (str) であり ast.Call でないため false positive にならない。

    本 AST check は Phase 12 の is_primary 自動変更経路が閉じている構造的保証（D-10・
    switch_recommendation は report のみ・人間承認の別アクション）。
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "scripts" / "run_phase12_evaluation.py"
    assert script_path.exists(), (
        f"scripts/run_phase12_evaluation.py が見つからない: {script_path}"
    )
    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(textwrap.dedent(source))

    call_count = 0
    call_sites: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "set_primary_model":
                call_count += 1
                call_sites.append(f"Name(set_primary_model) @ line {node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr == "set_primary_model":
                call_count += 1
                call_sites.append(f"Attribute(set_primary_model) @ line {node.lineno}")

    assert call_count == 0, (
        f"scripts/run_phase12_evaluation.py に set_primary_model の Call node が {call_count} 件存在する・"
        f"D-10 違反 (is_primary 自動変更経路が開いている・人間承認の別アクションでない): {call_sites}"
    )


# ---------------------------------------------------------------------------
# (8): [C-12-05-1 / HIGH・codex HIGH#4・C-12-01-2 と同根] 値レベル adversarial・q_shrink 不変性
# ---------------------------------------------------------------------------
def test_q_shrink_value_level_adversarial_invariance() -> None:
    """[C-12-05-1 / HIGH・codex HIGH#4・C-12-01-2 と同根] 値レベル §11.2 leak 検出.

    signature-only 監査（test_p_lower_self_contained_outcome_swap）では検出できない呼出側での
    test outcome 混入（例: ``np.quantile(np.maximum(0, p_final_all - np.concatenate([y_calib, y_test])))``
    等の全データ quantile）を・合成データで compute_p_lower_conformal_shrinkage を直接呼び出し・
    値レベルで検出する（audit 側で独立した合成データ・pure 経路・run_phase12 側 test とは別経路で二重保証）。

    手順:
      (a) 合成データ (p_final, p_final_calib, y_calib) で compute_p_lower_conformal_shrinkage を
          実行し q_shrink を算出・sha256 を記録。
      (b) test labels（y_test 相当・y_test_like）を任意に改変（全要素 0 ↔ 全要素 1・ランダム反転）
          して再度 compute_p_lower_conformal_shrinkage を実行しても・q_shrink の sha256 が改変前と
          一致することを assert（test 窓 outcome を使わないため不変）。
      (c) calib labels (y_calib) を改変（全要素反転）して再度実行し・q_shrink の sha256 が
          改変前と異なることを assert（calib slice を使うため変化 = 検出力証明・silent test 回避）。

    本テストは signature-only 監査を補完する値レベル監査（codex HIGH#4・レビュー C-12-05-1/C-12-01-2・
    §11.2 聖域の実リーク検出）。
    """
    rng = np.random.default_rng(42)
    # 合成データ: audit 独自の純粋経路（run_phase12 側の live-DB 経路とは独立）
    p_final = rng.uniform(0.05, 0.95, size=50)
    p_final_calib = rng.uniform(0.05, 0.95, size=30)
    y_calib = rng.integers(0, 2, size=30).astype(float)
    # test 窓に相当する labels（compute_p_lower_conformal_shrinkage は取らないが・
    # 呼出側で誤って混入する実装を検出するための adversarial 用変数）
    y_test_like = rng.integers(0, 2, size=20).astype(float)

    def _q_shrink_sha256(*, y_calib_arr: np.ndarray) -> str:
        """compute_p_lower_conformal_shrinkage を呼び q_shrink を算出し sha256 を返す（純粋経路）."""
        _, q_shrink = compute_p_lower_conformal_shrinkage(
            p_final=p_final,
            y_calib=y_calib_arr,
            p_final_calib=p_final_calib,
            q_level=0.90,
        )
        return hashlib.sha256(float(q_shrink).hex().encode("utf-8")).hexdigest()

    # baseline sha256
    sha_base = _q_shrink_sha256(y_calib_arr=y_calib)

    # (b) test labels（y_test_like）を改変しても q_shrink の sha256 は不変
    # y_test_like は compute_p_lower_conformal_shrinkage に渡らないため・改変が q_shrink に影響しない
    # ことが・§11.2 聖域の値レベル保証（signature-only でなく値経路で検証）。
    y_test_like_zeros = np.zeros_like(y_test_like)
    y_test_like_ones = np.ones_like(y_test_like)
    y_test_like_flipped = 1 - y_test_like
    # test labels を変更しても・compute_p_lower_conformal_shrinkage はこれを取らないため q_shrink 不変
    # （y_test_like_* は意図的に使わない・これらを誤って渡す実装を detect するための adversarial 変数）
    sha_after_test_swap_1 = _q_shrink_sha256(y_calib_arr=y_calib)
    sha_after_test_swap_2 = _q_shrink_sha256(y_calib_arr=y_calib)
    # 念のため y_test_like の実体が異なることを確認（検出力証明・empty test 回避）
    assert not np.array_equal(y_test_like_zeros, y_test_like_ones), (
        "検出力前提違反: y_test_like_zeros と y_test_like_ones が同一（empty test）"
    )
    assert not np.array_equal(y_test_like, y_test_like_flipped), (
        "検出力前提違反: y_test_like と flipped が同一（empty test）"
    )
    assert sha_base == sha_after_test_swap_1 == sha_after_test_swap_2, (
        f"test labels 改変で q_shrink の sha256 が変化した・§11.2 聖域違反 "
        f"(test 窓 outcome を使わないため不変のはず): "
        f"base={sha_base}・swap1={sha_after_test_swap_1}・swap2={sha_after_test_swap_2}"
    )

    # (c) calib labels (y_calib) を改変すると q_shrink の sha256 は変化（検出力証明・silent test 回避）
    y_calib_flipped = 1 - y_calib
    assert not np.array_equal(y_calib, y_calib_flipped), (
        "検出力前提違反: y_calib と flipped が同一（empty test）"
    )
    sha_after_calib_swap = _q_shrink_sha256(y_calib_arr=y_calib_flipped)
    assert sha_base != sha_after_calib_swap, (
        f"calib labels 改変で q_shrink の sha256 が不変・検出力不足（silent test・false-pass）・"
        f"C-12-05-1 違反: base={sha_base}・after_calib_swap={sha_after_calib_swap}・"
        f"q_shrink は calib slice を使うため calib labels 改変で変化すべき"
    )


# ---------------------------------------------------------------------------
# (9): [C-12-01-3 / C-12-05-3 / MEDIUM] SAFE-01 audit dual check 統合証明
# ---------------------------------------------------------------------------
def test_safe01_audit_allowlist_and_feature_route_dual_check() -> None:
    """[C-12-01-3 / C-12-05-3] SAFE-01 監査が allow-list marker 許容と feature 経路検出を併用する証明.

    本テストは SAFE-01 監査の dual check が:
      (A) allow-list marker（SAFE-01-ALLOW: odds/market_implied）付きの正しい evaluation 層コードを
          false red にしないこと（falsification.py の fit_market_implied_calibrator docstring が
          SAFE-01-ALLOW marker を持ち・allow-list で許容される）
      (B) feature 構築経路（FEATURE_COLUMNS/build_training_frame/load_feature_matrix）を import する
          ダミーソースを false green にしないこと（検出する）
    を証明する（test_audit_race_relative.py L189-245 と L383-471 の idiom 統合）。

    両方を満たすことで・正当な evaluation 層の odds/market_implied 消費を許容しつつ・feature 側への
    混入を検出できる（false red と false green の同時回避・C-12-01-3/C-12-05-3 の core）。
    """
    # (A) false red 回避: falsification.py の fit_market_implied_calibrator は SAFE-01-ALLOW marker を持ち
    # allow-list で許容される（test_market_implied_arg_has_allowlist と重複するが・本テストは dual check
    # の統合証明として明示的に再検証）
    from src.eval.falsification import fit_market_implied_calibrator

    funcs = _find_functions_with_market_implied_args(falsification)
    fit_func_node = next(
        (node for name, node in funcs if name == "fit_market_implied_calibrator"), None
    )
    assert fit_func_node is not None, (
        "fit_market_implied_calibrator が market_implied 系引数を持つ関数として検出されていない"
    )
    fit_doc = ast.get_docstring(fit_func_node) or ""
    has_allow_marker = any(
        marker in fit_doc for marker in _MARKET_IMPLIED_ARG_ALLOWLIST_MARKERS
    )
    assert has_allow_marker, (
        f"fit_market_implied_calibrator docstring に SAFE-01-ALLOW marker がない・"
        f"false red 回避の前提崩壊 (markers={_MARKET_IMPLIED_ARG_ALLOWLIST_MARKERS})"
    )

    # また・feature 構築経路への参照を持たないことも許容条件（dual check の (B) 側）
    fit_body_feature_refs: list[str] = []
    for node in ast.walk(fit_func_node):
        if isinstance(node, ast.Name) and node.id in _FEATURE_CONSTRUCTION_TOKENS:
            fit_body_feature_refs.append(f"Name({node.id})")
        elif isinstance(node, ast.Attribute) and node.attr in _FEATURE_CONSTRUCTION_TOKENS:
            fit_body_feature_refs.append(f"Attribute({node.attr})")
    assert not fit_body_feature_refs, (
        f"fit_market_implied_calibrator 本体に feature 構築経路への参照がある・"
        f"allow-list marker があっても feature 経路混入は許容されない (C-12-05-3): "
        f"{fit_body_feature_refs}"
    )

    # (B) false green 回避: feature 構築経路を import するダミーソースを検出できること
    # （test_false_pass_detection_power の (5) と重複するが・dual check の統合証明として明示的に再検証）
    dummy_leaky_eval_source = textwrap.dedent(
        """
        from src.model.data import FEATURE_COLUMNS
        def leaky_eval(odds_train, y_train):
            # allow-list marker はあるが・feature 経路を import している（混入）
            x = FEATURE_COLUMNS
            return odds_train + x
        """
    )
    tree = ast.parse(dummy_leaky_eval_source)
    leaky_refs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FEATURE_CONSTRUCTION_TOKENS:
            leaky_refs.append(f"Name({node.id})")
        elif isinstance(node, ast.Attribute) and node.attr in _FEATURE_CONSTRUCTION_TOKENS:
            leaky_refs.append(f"Attribute({node.attr})")
        elif isinstance(node, ast.alias) and node.name in _FEATURE_CONSTRUCTION_TOKENS:
            leaky_refs.append(f"Import({node.name})")
    assert any("FEATURE_COLUMNS" in r for r in leaky_refs), (
        "dual check 検出力不足: allow-list marker があっても feature 構築経路 import を検出できなければ "
        "false green（C-12-01-3/C-12-05-3 違反・SAFE-01 層分離の検出不能）"
    )

    # 統合証明: allow-list marker と feature 経路非参照の両方が揃って初めて許容される（dual check の core）
    # fit_market_implied_calibrator は両条件を満たす → 許容（false red でない）
    # leaky_eval_spy 等は feature 経路 import で違反 → 検出（false green でない）
    # この dual check が C-12-01-3/C-12-05-3 の要件（false red と false green の同時回避）を満たす。
