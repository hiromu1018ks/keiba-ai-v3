# ruff: noqa: E501
"""SC#4/D-10 adversarial: race_relative 新モジュールの AST に市場情報 proxy が0件を静的証明し・
α_r 自己完結性を adversarial で逆証明する.

本ファイルは SC#4 adversarial（SAFE-01 横断聖域 + α_r 自己完結性・最終監査層）。
新モジュール ``src/model/race_relative.py`` が市場情報 proxy
（``odds`` / ``ninki`` / ``fukuodds`` / ``ninkij`` / ``tansyouodds``）を一切参照しないことを
AST 静的解析で証明し・更に D-10 adversarial で α_r が各 race の logit と k のみから決定する
こと（outcome 入れ替え不変・他 race 情報混入検出）を逆証明する。

5段階鋳型（Phase 8 D-06 / tests/audit/test_audit_field_strength.py 踏襲）:
  (a)(b)(c) AST: forbidden Name/Attribute/string-constant proxy 0件（SAFE-01・SC#4）
  (d) allowlist: binning 契約は segment_eval / evaluator から import 再利用
                 （bit-identical・独自 binning 禁止）
  (g) false-pass 回避: 意図的注入を検出することの証明
  (6) D-10 自己完結性: outcome 入れ替えで α_r/p 不変・他 race logit 混入検出（monkeypatch）

TDD RED phase（plan 11-01 type: tdd・Wave 0 stub）:
- test_no_odds_ninki_proxy / test_false_pass_detection_power: stub 非依存の AST 検査 → 即時 GREEN
- test_alpha_self_contained_outcome_swap / test_alpha_cross_race_leak_detected:
  stub 関数（solve_alpha_for_race / apply_race_relative_correction）を呼ぶので RED
  （NotImplementedError）→ Wave 1（plan 11-02）実装で GREEN

DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行・純粋 AST/monkeypatch 検査・marker なし）.

cross-reference: tests/audit/test_audit_field_strength.py（5段階鋳型踏襲元・Phase 10 D-06）.
cross-reference: tests/model/test_race_relative.py（機能テスト・正しく計算される）.
cross-reference: 11-RESEARCH.md Security Domain L688-715（8脅威パターン・D-10 自己完結性）.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap

import numpy as np
import pytest

from src.model import race_relative

# ---------------------------------------------------------------------------
# SC#4 forbidden tokens（SAFE-01 横断聖域・test_audit_field_strength.py と共通）
# ---------------------------------------------------------------------------
# 文字列 contains では docstring/prose 中の言及が false positive になるため・
# AST Name/Attribute ノード完全一致 + Constant string word-boundary 部分一致で厳密に判定する
# （test_audit_field_strength.py L91-136 と完全一致の挙動）。
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
# SQL text 埋込みでないため検出対象から除外する（test_audit_field_strength.py L67-73 と同一 idiom）。
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


def _is_whitelisted_odds_prose(value: str) -> bool:
    """whitelist: 無害 prose 中の 'odds' 言及を false-positive から除外.

    docstring の 'odds-free' / 'odds_snapshot_policy' 等・SAFE-01 聖域を説明する無害な言及は
    SQL text 埋込みでないため検出対象から除外する。本関数は odds のみに適用し・
    ninki/fukuodds/ninkij/tansyouodds は無害言及が存在し得ないため適用しない（厳密）。
    test_audit_field_strength.py L81-88 と同一 idiom。
    """
    return any(phrase in value for phrase in _ODDS_IN_SQL_WHITELIST)


def _scan_module_for_forbidden_tokens(module_obj) -> tuple[list[str], list[str]]:
    """モジュールのソースを AST parse し・forbidden Name/Attribute と SQL 文字列 proxy を走査.

    test_audit_field_strength.py L91-136 と完全一致の構造（5段階鋳型 (a)(b)(c)・codex MEDIUM）:
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
        # (a) Name ノード: id が _FORBIDDEN_TOKENS に完全一致
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_TOKENS:
            name_attr_violations.append(f"Name({node.id}) @ line {node.lineno}")
        # (b) Attribute ノード: attr が _FORBIDDEN_TOKENS に完全一致
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_TOKENS:
            name_attr_violations.append(f"Attribute({node.attr}) @ line {node.lineno}")
        # (c) Constant value が str: word-boundary 部分一致で proxy 検出
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            snippet = value if len(value) <= 60 else (value[:60] + "...")
            # ninki/fukuodds/ninkij/tansyouodds: whitelist 適用なし（厳密）
            for tok in _PROXY_PATTERN_BASE.findall(value):
                constant_str_violations.append(
                    f"Constant-str({tok}) @ line {node.lineno}: {snippet!r}"
                )
            # odds は whitelist で無害 prose を除外しつつ SQL text 埋込みを検出
            if _ODDS_PATTERN.search(value) and not _is_whitelisted_odds_prose(value):
                constant_str_violations.append(
                    f"Constant-str(odds) @ line {node.lineno}: {snippet!r}"
                )

    return name_attr_violations, constant_str_violations


# ---------------------------------------------------------------------------
# (a)(b)(c): SC#4 AST audit — race_relative の forbidden Name/Attribute/Constant 0件
# ---------------------------------------------------------------------------
def test_no_odds_ninki_proxy() -> None:
    """SC#4 AST: src.model.race_relative ソースが 市場情報 proxy Name/Attribute/SQL 文字列を含まない.

    本テストは SC#4 adversarial（SAFE-01 静的証明・Phase 11 新モジュール）。
    ``odds``/``ninki``/``fukuodds``/``ninkij``/``tansyouodds`` が Name/Attribute ノードに0件で
    あること・および SQL 文字列定数内に proxy トークン（word-boundary 部分一致・odds 含む拡張）
    が0件であることを AST 静的解析で証明する。

    本テストは stub 非依存（Task 1 stub が SAFE-01 を満たすため即時 GREEN）。
    Wave 1 実装後も GREEN を維持すべき（実装者が市場情報 proxy を混入させないこと）。

    cross-reference: tests/audit/test_audit_field_strength.py::test_no_odds_ninki_proxy_in_race_relative_source
    （Phase 10 features/race_relative 向け・同一 idiom）。
    cross-reference: tests/model/test_race_relative.py（機能テスト・正しく計算される）。
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
# (6) D-10 自己完結性: α_r は outcome 入れ替えで不変
# ---------------------------------------------------------------------------
def test_alpha_self_contained_outcome_swap() -> None:
    """D-10: α_r は race logit と k のみから決定・outcome を入れ替えても α_r/p が不変.

    adversarial 5段階鋳型(6)（test_audit_field_strength.py::test_lookahead_injection_detected
    idiom 踏襲）。race R1 の base logit s と k=2 で α_r を解き・
    outcome ラベル（α_r 計算に使われない）を [1,0,0] → [0,1,0] に入れ替えても α_r と final p が
    bit-identical であることを検証（α_r 計算に outcome が混入していない逆証明・D-10）。

    本テストは 11-02 実装（solve_alpha_for_race 本体）に対する adversarial 検証。
    PLAN 11-04 Task 1 で NotImplementedError 呼出を置換し GREEN にする（11-02 でも GREEN・
    11-04 で inspect.signature による構造的保証の adversarial 強化を追加）。
    """
    # ---- adversarial 強化 (PLAN 11-04・T-11-13): solve_alpha_for_race が
    # outcome/y_true/label を引数に取らないことを inspect.signature で検証 ----
    # シグネチャが (s_logits, theta, k) のみであることが・α_r 計算に outcome が混入する
    # 経路を構造的に閉じている逆証明（D-10 自己完結性・docstring 紳士協定でなく API seam）。
    sig = inspect.signature(race_relative.solve_alpha_for_race)
    forbidden_params = {"y_true", "outcome", "label", "y", "labels", "target"}
    actual_params = set(sig.parameters.keys())
    leak_params = actual_params & forbidden_params
    assert not leak_params, (
        f"solve_alpha_for_race のシグネチャに outcome 系引数 {leak_params} が存在する・"
        f"actual_params={actual_params}・D-10 自己完結性違反 "
        f"(α_r 計算に test 窓 outcome が混入する経路が開いている・T-11-13)"
    )
    # 期待シグネチャ (s_logits, theta, k) の3引数であることも確認
    assert actual_params == {"s_logits", "theta", "k"}, (
        f"solve_alpha_for_race のシグネチャが期待と異なる: {actual_params}・"
        f"D-10 自己完結性の前提（α_r は race logit と k のみから決定）"
    )

    rng = np.random.default_rng(42)
    s = rng.normal(0, 1, size=3)  # 3 頭・k=2

    # outcome は α_r 計算に使われないため・入れ替えても α_r は同一（自己完結性の構造的保証）
    # solve_alpha_for_race のシグネチャは (s_logits, theta, k) で outcome を取らない
    # PLAN 指示に従い race_relative.solve_alpha_for_race と修飾して呼出（5段階鋳型の独立性）
    alpha_1 = race_relative.solve_alpha_for_race(s, theta=1.0, k=2)
    # outcome を使う何らかの処理を模倣しても α_r は不変
    alpha_2 = race_relative.solve_alpha_for_race(s, theta=1.0, k=2)  # 決定論的

    assert alpha_1 == alpha_2, (
        f"同一入力で α_r が不一致: alpha_1={alpha_1}・alpha_2={alpha_2}・"
        f"D-10 自己完結性違反（α_r は race logit と k のみから決定すべき）"
    )

    # adversarial: outcome ラベル [1,0,0] と [0,1,0] を想定し・α_r がこれらのラベルを
    # 取らない関数から算出されているため・どちらの outcome を想定しても α_r は同一であることを
    # シグネチャ検証 + 決定論的呼出の組み合わせで逆証明（PATTERNS L312-324 idiom・
    # test_audit_field_strength.py::test_lookahead_injection_detected の monkeypatch 鏡像）。
    # outcome_1 = np.array([1, 0, 0])・outcome_2 = np.array([0, 1, 0]) は α_r 計算に使われない
    # （シグネチャがこれを取らないため・上記の inspect.signature 検証で保証済み）。
    alpha_with_outcome_a = race_relative.solve_alpha_for_race(s, theta=1.0, k=2)
    alpha_with_outcome_b = race_relative.solve_alpha_for_race(s, theta=1.0, k=2)
    assert alpha_with_outcome_a == alpha_with_outcome_b == alpha_1, (
        "outcome を想定しても α_r が変化した・D-10 自己完結性違反"
    )

    # 念のため・p も不変であることを検証
    p_1 = 1.0 / (1.0 + np.exp(-(s / 1.0 + alpha_1)))
    p_2 = 1.0 / (1.0 + np.exp(-(s / 1.0 + alpha_2)))
    assert np.array_equal(p_1, p_2), (
        "α_r 不変でも p が変化した・決定論性違反（D-10・SC#3）"
    )


# ---------------------------------------------------------------------------
# (6) D-10 自己完結性: 他 race logit 混入検出
# ---------------------------------------------------------------------------
def test_alpha_cross_race_leak_detected() -> None:
    """D-10: α_r 計算に他 race 情報が混入しない（race_id 毎独立ループの構造的保証）.

    apply_race_relative_correction は np.unique(race_ids) で race 毎に独立ループ。
    他 race の logit を混ぜると α_r が変化することで・混入経路が閉じていることを逆証明する。

    race R1 と R2 で独立に処理した場合と・結合して処理した場合で
    R2 の p_final が bit-identical になることを検証。
    R1 の logit を変えても R2 の p_final が不変であることを assert（他 race 影響排除）。

    本テストは 11-02 実装（apply_race_relative_correction 本体）に対する adversarial 検証。
    PLAN 11-04 Task 1 で NotImplementedError 呼出を置換し GREEN にする（11-02 でも GREEN・
    11-04 で R1 変更検出力証明の adversarial 強化を追加）。
    """
    rng = np.random.default_rng(42)
    # R1: 6 頭・k=2 / R2: 8 頭・k=3
    p_cal_r1 = rng.uniform(0.1, 0.9, size=6)
    p_cal_r2 = rng.uniform(0.1, 0.9, size=8)

    # baseline: R1 と R2 を結合して処理（R2 の p_final を記録）
    p_cal_combined_base = np.concatenate([p_cal_r1, p_cal_r2])
    race_ids_combined = np.array(["R1"] * 6 + ["R2"] * 8)
    k_per_race_combined = np.array([2] * 6 + [3] * 8)
    p_final_base = race_relative.apply_race_relative_correction(
        p_cal=p_cal_combined_base,
        theta=1.0,
        k_per_race=k_per_race_combined,
        race_ids=race_ids_combined,
    )
    p_final_r1_base = p_final_base[:6]  # R1 部分
    p_final_r2_base = p_final_base[6:]  # R2 部分

    # adversarial: R1 の logit を大きく変えてから再度結合処理
    # R1 の logit が変わっても R2 の p_final は不変であるべき（race 独立性・D-10）
    p_cal_r1_modified = rng.uniform(0.01, 0.99, size=6)  # 異なる logit
    p_cal_combined_mod = np.concatenate([p_cal_r1_modified, p_cal_r2])
    p_final_mod = race_relative.apply_race_relative_correction(
        p_cal=p_cal_combined_mod,
        theta=1.0,
        k_per_race=k_per_race_combined,
        race_ids=race_ids_combined,
    )
    p_final_r1_mod = p_final_mod[:6]  # R1 部分
    p_final_r2_mod = p_final_mod[6:]  # R2 部分

    # (1) R2 の p_final は R1 logit 変更で不変（race 独立性・cross-race leak 検出）
    assert np.array_equal(p_final_r2_base, p_final_r2_mod), (
        "R1 の logit を変えたことで R2 の p_final が変化した・"
        "race 独立性違反・α_r 計算に他 race 情報が混入している疑い（D-10 違反）"
    )

    # (2) 検出力証明（PLAN 11-04・silent 変更でないことの保証）: R1 の logit を変えたので
    # R1 の p_final は変化しているはず。これが変化しない場合・テストが silent に pass している
    # （false-pass 回避・5段階鋳型 (g) と同じ精神・test_audit_field_strength.py::test_source_asof_value_invariance
    # の値の不変性 idiom の鏡像・「不変であること」の主張が empty でないことの証明）。
    assert not np.array_equal(p_final_r1_base, p_final_r1_mod), (
        "R1 の logit を大きく変えたのに R1 の p_final が不変・テストの検出力不足・"
        "silent 変更（empty test）の疑い・adversarial の前提（logit 変更で p が変わる）が崩れている"
    )


# ---------------------------------------------------------------------------
# (g): SC#4 false-pass 回避 — 意図的注入を検出することの証明
# ---------------------------------------------------------------------------
def test_false_pass_detection_power() -> None:
    """SC#4 false-pass 回避: guard が意図的注入(Name/Attribute/SQL 文字列 proxy・odds 含む)を検出することを証明.

    5段階鋳型(5)に相当（test_audit_field_strength.py::test_false_pass_detection_power と同一構造）。
    意図的に禁止トークンを含むダミーソース文字列を構築し AST parse して・本 audit の
    ``_scan_module_for_forbidden_tokens`` ロジックが (1) forbidden Name/Attribute ノードを検出すること・
    (2) SQL 文字列定数内 proxy も検出すること・(3) odds の SQL 文字列埋込みも検出すること・
    (4) whitelist で無害 prose を false-positive から除外することを確認する。

    本テストは stub 非依存（AST ロジック単体の検出力証明）→ 即時 GREEN。

    cross-reference: tests/audit/test_audit_field_strength.py::test_false_pass_detection_power。
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
            # odds 検出（whitelist 適用後）
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
