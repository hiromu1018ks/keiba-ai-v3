# ruff: noqa: E501  (長い docstring を保持するため行長は緩和)
"""Phase 12 Plan 02 Task 2: EV 層 p_lower 切替検証契約 (EV-01・D-03・Pitfall 7・SAFE-01).

本テストは 12-02-PLAN.md Task 2 で新設する。test_ev/ 配下の既存 test と併用し・
Phase 12 SC#1 p_lower × odds_lower の EV 計算と投票層定義の明示を機械保証する.

検証内容 (PLAN Task 2 behavior Test 1-8):
- Test 1 (EV_lower=p_lower×odds_lower): compute_ev_and_rank(df, p_col='p_fukusho_hit_lower') で
  EV_lower = p_fukusho_hit_lower × fuku_odds_lower (D-03・入力列差し替え)
- Test 2 (p_col 既定値後方互換): compute_ev_and_rank(df) (p_col 省略) は従来通り
  p_fukusho_hit × fuku_odds_lower (v1.0 binary 呼出互換)
- Test 3 (purchase_simulator p_min_base='p_lower'): select_bets(df, p_col='p_fukusho_hit_lower',
  p_min_base='p_lower') で p_min=0.15 を p_fukusho_hit_lower に対して適用 (Pitfall 7)
- Test 4 (p_min_base='p' 従来): select_bets(df, p_min_base='p') は p_fukusho_hit >= 0.15 (従来・後方互換)
- Test 5 (mergesort byte-reproducible): select_bets を2回呼出し・selected 行が bit-identical
- Test 6 (C-12-02-4・report p_lower 表示・既存 report regression なし): REPORT_COLUMNS に
  p_lower 系が表示可能・かつ p_lower 系キーが欠損した既存 backtest dict で KeyError にならず
  NaN/省略で表示される (.get(c) または Phase 12 専用 reports 分離)
- Test 7 (SAFE-01・EV 層): ev_rank / purchase_simulator が FEATURE_COLUMNS を import しない (AST)
- Test 8 (C-12-02-3・_rank p_col 伝播): _rank 関数が p_col='p_fukusho_hit_lower' を受け取り
  S/A/B rank の p_min 判定が p_fukusho_hit ではなく p_fukusho_hit_lower に対して行われる
  (EV 計算と rank 条件の確率基準一致・投票層定義の分裂回避)

参考: 12-02-PLAN.md / 12-CONTEXT.md D-03 / 12-RESEARCH.md Pattern 3 / 12-PATTERNS.md ev_rank・
      purchase_simulator・report / 12-REVIEWS.md C-12-02-3・C-12-02-4 / src/ev/ev_rank.py /
      src/ev/purchase_simulator.py / src/ev/report.py.
"""

from __future__ import annotations

import ast
import inspect

import numpy as np
import pandas as pd
import pytest

from src.ev.ev_rank import _rank, compute_ev_and_rank
from src.ev.purchase_simulator import select_bets
from src.ev.report import REPORT_COLUMNS, generate_report


# ---------------------------------------------------------------------------
# 共通 helper: p と p_lower の両方を持つ合成 df
# ---------------------------------------------------------------------------
def _build_synthetic_pred_df(n_races: int = 3, seed: int = 42) -> pd.DataFrame:
    """p_fukusho_hit と p_fukusho_hit_lower の両方を持つ合成予測+オッズ df を構築する.

    各レース8頭・race_key 一意. p_lower は常に p <= p_lower を満たす (D-01 max(0, p-q_shrink) <= p).
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for r in range(n_races):
        race_key = f"2024-01-0{r + 1}-01-01-{r + 1}-01-r{r}"
        for umaban in range(1, 9):
            p = float(np.clip(rng.normal(0.25, 0.1), 0.05, 0.6))
            # p_lower = p - q_shrink (q_shrink > 0) → p_lower < p を保証
            p_lower = max(0.0, p - 0.08)
            rows.append(
                {
                    "race_key": race_key,
                    "umaban": umaban,
                    "p_fukusho_hit": p,
                    "p_fukusho_hit_lower": p_lower,
                    "fuku_odds_lower": float(np.clip(rng.normal(3.5, 1.0), 1.2, 10.0)),
                    "fuku_odds_upper": float(np.clip(rng.normal(5.0, 1.5), 1.5, 15.0)),
                    "is_fukusho_sale_available": True,
                    "is_model_eligible": True,
                }
            )
    df = pd.DataFrame(rows)
    df = df.sort_values(["race_key", "umaban"], kind="mergesort").reset_index(drop=True)
    return df


# ===========================================================================
# Test 1: EV_lower=p_lower×odds_lower (p_col='p_fukusho_hit_lower')
# ===========================================================================
def test_compute_ev_and_rank_p_lower_column_substitution():
    """compute_ev_and_rank(df, p_col='p_fukusho_hit_lower') で EV_lower = p_fukusho_hit_lower × fuku_odds_lower
    (D-03・入力列差し替え)."""
    df = _build_synthetic_pred_df()
    out = compute_ev_and_rank(df, p_col="p_fukusho_hit_lower")
    # EV_lower = p_lower × odds_lower (D-03・入力列差し替え)
    expected_ev_lower = df["p_fukusho_hit_lower"] * df["fuku_odds_lower"]
    np.testing.assert_allclose(out["EV_lower"].to_numpy(), expected_ev_lower.to_numpy(), rtol=1e-12)
    # EV_upper も p_lower ベース (D-03・入力列差し替え)
    expected_ev_upper = df["p_fukusho_hit_lower"] * df["fuku_odds_upper"]
    np.testing.assert_allclose(out["EV_upper"].to_numpy(), expected_ev_upper.to_numpy(), rtol=1e-12)
    # recommend_rank 列が付与されていること
    assert "recommend_rank" in out.columns


# ===========================================================================
# Test 2: p_col 既定値後方互換 (p_col 省略は従来通り p_fukusho_hit)
# ===========================================================================
def test_compute_ev_and_rank_default_p_col_backward_compat():
    """compute_ev_and_rank(df) (p_col 省略) は従来通り p_fukusho_hit × fuku_odds_lower (v1.0 binary 互換)."""
    df = _build_synthetic_pred_df()
    out_default = compute_ev_and_rank(df)  # p_col 省略
    out_explicit = compute_ev_and_rank(df, p_col="p_fukusho_hit")
    # 既定値は 'p_fukusho_hit'
    expected_ev_lower = df["p_fukusho_hit"] * df["fuku_odds_lower"]
    np.testing.assert_allclose(
        out_default["EV_lower"].to_numpy(), expected_ev_lower.to_numpy(), rtol=1e-12
    )
    # 省略と明示 'p_fukusho_hit' は同一結果 (後方互換・A5)
    np.testing.assert_allclose(
        out_default["EV_lower"].to_numpy(), out_explicit["EV_lower"].to_numpy(), rtol=1e-12
    )


# ===========================================================================
# Test 8: [C-12-02-3 / MEDIUM] _rank p_col 伝播
# ===========================================================================
def test_rank_p_col_propagation_changes_threshold_base():
    """[C-12-02-3 MEDIUM] _rank 関数が p_col='p_fukusho_hit_lower' を受け取り・S/A/B rank の
    p_min 判定が p_fukusho_hit ではなく p_fukusho_hit_lower に対して行われる (EV と rank の確率基準一致).

    境界例: p_fukusho_hit = 0.30 (S rank p_min=0.25 を満たす)・p_fukusho_hit_lower = 0.10
    (S rank p_min=0.25 を満たさない)・EV_lower と odds_lower は十分高い・を与え・
    p_col='p_fukusho_hit' では S・p_col='p_fukusho_hit_lower' では S でない (A/B/D のいずれか) ことを検証.
    """
    # 境界 row: p=0.30・p_lower=0.10・EV_lower と odds_lower は十分高い
    # EV_lower は事前計算しておく (_rank は df.apply 経由で呼ばれる前提で row 単体の EV_lower を参照).
    # EV_lower を p=0.30 でも p_lower=0.10 でも十分高い (S の ev_lower_min=1.20 を超える) ように
    # fuku_odds_lower=10.0 とする・p=0.30 の場合は EV_lower=3.0・p_lower=0.10 の場合は EV_lower=1.0.
    boundary_row_p_high = {
        "race_key": "test-r1",
        "umaban": 1,
        "p_fukusho_hit": 0.30,  # >= 0.25 (S rank p_min)
        "p_fukusho_hit_lower": 0.10,  # < 0.25 (S rank p_min を満たさない)
        # p_col='p_fukusho_hit' の場合の EV_lower = 0.30 * 10 = 3.0
        # p_col='p_fukusho_hit_lower' の場合の EV_lower = 0.10 * 10 = 1.0 (★これは呼出側で計算し直す)
        "EV_lower": 3.0,  # 初期値は p_col='p_fukusho_hit' 相当
        "fuku_odds_lower": 10.0,
        "fuku_odds_upper": 15.0,
        "is_fukusho_sale_available": True,
        "is_model_eligible": True,
    }
    df = pd.DataFrame([boundary_row_p_high])

    # p_col='p_fukusho_hit' の場合: rank 条件の p_min 判定は p_fukusho_hit (0.30) に対して
    # → S の p_min=0.25 を満たし・EV_lower=3.0 >= 1.20・odds_lower=10.0 >= 1.5 → S rank
    rank_p = _rank(df.iloc[0], p_col="p_fukusho_hit")
    assert rank_p == "S", f"p_col='p_fukusho_hit' では S rank (p=0.30 >= 0.25). got={rank_p}"

    # p_col='p_fukusho_hit_lower' の場合: rank 条件の p_min 判定は p_fukusho_hit_lower (0.10) に対して
    # → S の p_min=0.25 も A の p_min=0.20 も B の p_min=0.15 も満たさない → C or D
    # (EV_lower=0.10*10=1.0 >= C の ev_lower_min=1.00 → C rank)
    # 注: EV_lower も p_col='p_fukusho_hit_lower' 相当 (0.10*10=1.0) に更新する
    # (compute_ev_and_rank が p_col で EV 計算と rank 判定を整合させるため・row 単体テストでも再現).
    df_lower = df.copy()
    df_lower.loc[0, "EV_lower"] = 0.10 * 10.0  # p_lower ベースの EV_lower
    rank_lower = _rank(df_lower.iloc[0], p_col="p_fukusho_hit_lower")
    assert rank_lower != "S", (
        f"p_col='p_fukusho_hit_lower' では S rank でない (p_lower=0.10 < 0.25). got={rank_lower}"
    )
    assert rank_lower in ("A", "B", "C", "D"), f"rank は S/A/B/C/D のいずれか. got={rank_lower}"


def test_compute_ev_and_rank_p_col_propagates_to_rank():
    """compute_ev_and_rank(df, p_col='p_fukusho_hit_lower') が _rank に p_col を伝播し・
    recommend_rank 列が p_col に従って算出される (C-12-02-3・EV 計算と rank 条件の確率基準一致)."""
    df = _build_synthetic_pred_df(n_races=2)
    # p_col='p_fukusho_hit' と p_col='p_fukusho_hit_lower' で rank 結果が異なる行が
    # 存在することを確認 (p_lower < p なので rank が変わる可能性がある).
    out_p = compute_ev_and_rank(df, p_col="p_fukusho_hit")
    out_lower = compute_ev_and_rank(df, p_col="p_fukusho_hit_lower")
    # 全行で rank が等しいわけではない (p_lower の方が低いので rank が下がる行が最低1行はある)
    ranks_p = out_p["recommend_rank"].to_numpy()
    ranks_lower = out_lower["recommend_rank"].to_numpy()
    # 全行で同一だと p_col 伝播していない (silent bug). 少なくとも1行は違うことを検証.
    assert not np.array_equal(ranks_p, ranks_lower), (
        "compute_ev_and_rank の p_col が _rank に伝播していること (C-12-02-3・"
        "p_col='p_fukusho_hit' と 'p_fukusho_hit_lower' で rank 結果が変わる行がある)"
    )


# ===========================================================================
# Test 3: purchase_simulator p_min_base='p_lower'
# ===========================================================================
def test_select_bets_p_min_base_p_lower():
    """select_bets(df, p_col='p_fukusho_hit_lower', p_min_base='p_lower') で p_min=0.15 を
    p_fukusho_hit_lower に対して適用 (Pitfall 7・投票層の定義明示)."""
    df = _build_synthetic_pred_df(n_races=2)
    # EV_lower と odds_lower を high に設定して・p_min 条件だけを変える
    df = df.copy()
    df["EV_lower"] = df["p_fukusho_hit_lower"] * df["fuku_odds_lower"]
    df["EV_upper"] = df["p_fukusho_hit_lower"] * df["fuku_odds_upper"]
    df["recommend_rank"] = "B"
    # 全行 fuku_odds_lower >= 1.5 を保証 (odds 条件が p_min 比較に影響しないように)
    df["fuku_odds_lower"] = df["fuku_odds_lower"].clip(lower=2.0)
    # EV_lower >= 1.05 を保証 (EV 条件が p_min 比較に影響しないように)
    df["EV_lower"] = df["EV_lower"].clip(lower=1.10)

    # p_min_base='p_lower': p_fukusho_hit_lower >= 0.15 で filter
    selected_lower = select_bets(
        df, p_col="p_fukusho_hit_lower", p_min_base="p_lower"
    )
    # 選択された全行の p_fukusho_hit_lower >= 0.15 (p_min 条件が p_lower に適用された)
    if len(selected_lower) > 0:
        assert (selected_lower["p_fukusho_hit_lower"] >= 0.15).all(), (
            "p_min_base='p_lower' は p_fukusho_hit_lower >= 0.15 で filter (Pitfall 7)"
        )

    # p_min_base='p' (従来): p_fukusho_hit >= 0.15 で filter
    selected_p = select_bets(df, p_col="p_fukusho_hit", p_min_base="p")
    if len(selected_p) > 0:
        assert (selected_p["p_fukusho_hit"] >= 0.15).all(), (
            "p_min_base='p' は p_fukusho_hit >= 0.15 で filter (従来・後方互換)"
        )


# ===========================================================================
# Test 4: p_min_base='p' 従来 (後方互換)
# ===========================================================================
def test_select_bets_p_min_base_p_backward_compat():
    """select_bets(df, p_min_base='p') は p_fukusho_hit >= 0.15 (従来・後方互換・A5)."""
    df = _build_synthetic_pred_df(n_races=2)
    df = df.copy()
    df["EV_lower"] = df["p_fukusho_hit"] * df["fuku_odds_lower"]
    df["EV_upper"] = df["p_fukusho_hit"] * df["fuku_odds_upper"]
    df["recommend_rank"] = "B"
    df["fuku_odds_lower"] = df["fuku_odds_lower"].clip(lower=2.0)
    df["EV_lower"] = df["EV_lower"].clip(lower=1.10)

    # 既定値 (p_col・p_min_base 省略) は従来互換
    selected_default = select_bets(df)
    selected_explicit_p = select_bets(df, p_col="p_fukusho_hit", p_min_base="p")
    # 既定と明示 'p' は同一 row 集合 (後方互換・A5)
    assert set(selected_default.index) == set(selected_explicit_p.index), (
        "select_bets 既定 (p_col/p_min_base 省略) は p_col='p_fukusho_hit'・p_min_base='p' と同一 (A5)"
    )


# ===========================================================================
# Test 5: mergesort byte-reproducible (select_bets を2回呼出し bit-identical)
# ===========================================================================
def test_select_bets_byte_reproducible_mergesort():
    """select_bets を2回呼出し・selected 行が bit-identical (mergesort・seed 非依存・§19.1)."""
    df = _build_synthetic_pred_df(n_races=4, seed=123)
    df = df.copy()
    df["EV_lower"] = df["p_fukusho_hit_lower"] * df["fuku_odds_lower"]
    df["EV_upper"] = df["p_fukusho_hit_lower"] * df["fuku_odds_upper"]
    df["recommend_rank"] = "B"

    selected1 = select_bets(df, p_col="p_fukusho_hit_lower", p_min_base="p_lower")
    selected2 = select_bets(df, p_col="p_fukusho_hit_lower", p_min_base="p_lower")
    # 全列含めて bit-identical (mergesort で決定論的タイブレーク・seed 非依存)
    pd.testing.assert_frame_equal(selected1.reset_index(drop=True), selected2.reset_index(drop=True))


# ===========================================================================
# Test 6: [C-12-02-4 / MEDIUM] report p_lower 表示・既存 report regression なし
# ===========================================================================
def test_report_p_lower_display_no_regression_on_legacy_dicts(tmp_path):
    """[C-12-02-4 MEDIUM] REPORT_COLUMNS 拡張 (p_lower 系表示) は Phase 5 既存 report dict
    (p_lower 系キー欠損) で KeyError にならず NaN/省略で表示される (.get(c) または Phase 12 専用
    reports 分離)."""
    # Phase 5 既存 report dict (p_lower 系キーを含まない・v1.0 binary backtest 想定)
    legacy_dict = {
        "backtest_id": "bt1-lgb-v1",
        "bt_name": "BT1 train2022 test2023",
        "odds_policy": "30min_before",
        "model_type": "lightgbm",
        "recovery_rate": 0.85,
        "P/L": -150,
        "max_DD": -2000,
        "selected": 100,
        "effective_bet": 10000,
        "refund": 500,
        "hit_rate": 0.32,
    }
    # generate_report は既存 backtest dict (p_lower 系欠損) で KeyError を起こさず完了する.
    # (REPORT_COLUMNS に p_lower 系を追加しないか・追加しても .get(c) で欠損を NaN 許容)
    md_path, json_path = generate_report(
        [legacy_dict], output_dir=str(tmp_path), jodds_status="synthetic"
    )
    assert md_path.exists()
    assert json_path.exists()
    # JSON が valid で読めること (regression がないことの最終確認)
    import json

    with json_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    assert "comparison_table" in payload
    assert len(payload["comparison_table"]) == 1
    # 既存キーが保持されていること
    row = payload["comparison_table"][0]
    assert row["backtest_id"] == "bt1-lgb-v1"
    assert row["recovery_rate"] == 0.85


def test_report_phase12_p_lower_columns_display(tmp_path):
    """[C-12-02-4 MEDIUM] Phase 12 専用 reports または REPORT_COLUMNS 拡張で・p_lower 系
    (p_fukusho_hit_lower・q_level・q_shrink) が表示可能. Phase 12 専用 dict を渡した場合に
    これらのキーが表示されるか・REPORT_COLUMNS に含まれるかを検証."""
    from src.ev.report import REPORT_COLUMNS_PHASE12

    # Phase 12 専用 report dict (p_lower 系キーを含む)
    phase12_dict = {
        "backtest_id": "bt1-lgbrr-v1",
        "bt_name": "BT1 race-relative p_lower",
        "odds_policy": "30min_before",
        "model_type": "lightgbm_rr",
        "recovery_rate": 0.88,
        "P/L": 200,
        "max_DD": -1500,
        "selected": 95,
        "effective_bet": 9500,
        "refund": 300,
        "hit_rate": 0.34,
        "p_fukusho_hit_lower": 0.18,
        "p_lower_q_level": 0.90,
        "p_lower_q_shrink": 0.07,
    }
    md_path, json_path = generate_report(
        [phase12_dict],
        output_dir=str(tmp_path),
        jodds_status="complete",
        report_columns=REPORT_COLUMNS_PHASE12,
        report_basename="12-evaluation",
    )
    assert md_path.exists()
    assert json_path.exists()
    # basename 切替で reports/12-evaluation.{md,json} が生成される
    assert md_path.name == "12-evaluation.md"
    assert json_path.name == "12-evaluation.json"
    # Phase 12 dict の p_lower 系キーが JSON comparison_table で参照可能であること
    import json

    with json_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    row = payload["comparison_table"][0]
    # p_lower 系キーは存在すれば保持される (REPORT_COLUMNS_PHASE12 に含まれる)
    assert "p_fukusho_hit_lower" in row
    assert row["p_fukusho_hit_lower"] == 0.18
    assert row["p_lower_q_level"] == 0.90
    assert row["p_lower_q_shrink"] == 0.07
    # JSON constants の REPORT_COLUMNS に p_lower 系が含まれる (Phase 12 専用 tuple 使用)
    assert "p_fukusho_hit_lower" in payload["constants"]["REPORT_COLUMNS"]
    assert "p_lower_q_level" in payload["constants"]["REPORT_COLUMNS"]
    # markdown にも p_lower 系ヘッダが含まれる
    md_content = md_path.read_text(encoding="utf-8")
    assert "p_fukusho_hit_lower" in md_content


# ===========================================================================
# Test 7: SAFE-01・EV 層が FEATURE_COLUMNS を import しない (AST)
# ===========================================================================
def test_ev_layer_no_feature_columns_import_safe01():
    """[SAFE-01] ev_rank / purchase_simulator が FEATURE_COLUMNS / build_training_frame /
    load_feature_matrix を import しない (AST 検証・feature 構築経路からの切り離し)."""
    import src.ev.ev_rank as ev_rank_mod
    import src.ev.purchase_simulator as purchase_simulator_mod

    forbidden_names = {"FEATURE_COLUMNS", "build_training_frame", "load_feature_matrix"}

    def _scan_imports(module_obj) -> list[str]:
        """モジュールの AST を走査し・forbidden な import があれば名前を返す."""
        source = inspect.getsource(module_obj)
        tree = ast.parse(source)
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in forbidden_names or alias.asname in forbidden_names:
                        violations.append(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    full = alias.name + "." + alias.asname if alias.asname else alias.name
                    for fn in forbidden_names:
                        if fn in full:
                            violations.append(fn)
        return violations

    violations_rank = _scan_imports(ev_rank_mod)
    assert not violations_rank, (
        f"ev_rank が feature 構築経路を import している (SAFE-01 違反): {violations_rank}"
    )
    violations_purchase = _scan_imports(purchase_simulator_mod)
    assert not violations_purchase, (
        f"purchase_simulator が feature 構築経路を import している (SAFE-01 違反): {violations_purchase}"
    )
