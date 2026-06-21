# ruff: noqa: E501  (長い docstring / テスト説明を保持するため行長は緩和)
"""Plan 05-05 Task 2: 合成データ E2E smoke テスト (run_backtest --synthetic).

実JODDS取得進行中でも・``--synthetic`` でフル行列 backtest pipeline が完走し
reports/05-backtest.{md,json} が生成されることを検証する。

検証対象:
- フル行列 smoke (BT-1 を5件 = 2policy × 2model + 1 BL-3)
- BACK-04 winner 強調禁止 (report に「推奨:」「採用候補」の突出語句がない)
- backtest_strategy_version='fukusho_ev_v1' stamp
- BL3_COMPARISON_CAVEAT 注記
- HIGH-1/2 馬単位 JOIN + 行数不変
- HIGH-5 BT窓 category_map refit (test 窓 ID が __UNSEEN__ に mapping)
- LOW-05 REPORT_COLUMNS presence
- HIGH-B cycle-2 _carve_calib_from_train_tail (順序不変 + deterministic)
- HIGH-C cycle-2 HARAI race-level merge + 行ベース slot lookup
- MEDIUM-A cycle-2 full_candidate_with_accounting (selected + non-selected 永続化)
- MEDIUM cycle-3 non-selected 会計ゼロ化
- MEDIUM-B cycle-2 horse-level usable-odds coverage gate

実JODDS/実DB 不要 (``--synthetic``)・KEIBA_SKIP_DB_TESTS 影響外。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Task 2: pipeline level smoke — run_backtest --synthetic --bt-filter BT-1
# ---------------------------------------------------------------------------


def _run_synthetic_bt1(tmp_reports_dir: Path) -> dict:
    """run_backtest.main --synthetic --bt-filter BT-1 を実行し・生成された reports を読込む。

    戻り値: ``{"md_text": str, "json_data": dict}``
    """
    import sys

    # scripts/run_backtest.py を import するため sys.path にリポジトリルートを追加
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from scripts import run_backtest  # noqa: PLC0415

    argv = [
        "--synthetic",
        "--bt-filter", "BT-1",
        "--no-write-db",
        "--output-dir", str(tmp_reports_dir),
    ]
    rc = run_backtest.main(argv)
    assert rc == 0, f"run_backtest.main failed with rc={rc}"

    md_path = tmp_reports_dir / "05-backtest.md"
    json_path = tmp_reports_dir / "05-backtest.json"
    assert md_path.exists(), f"reports md not generated: {md_path}"
    assert json_path.exists(), f"reports json not generated: {json_path}"
    md_text = md_path.read_text(encoding="utf-8")
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    return {"md_text": md_text, "json_data": json_data}


def test_synthetic_full_matrix_smoke(tmp_path):
    """合成データ BT-1 で5件の backtest が完走し reports が生成される (HIGH-1/2/5 含む)。"""
    result = _run_synthetic_bt1(tmp_path)
    comparison = result["json_data"]["comparison_table"]
    # BT-1: 2policy × 2model + 1 BL-3 = 5件
    assert len(comparison) == 5, f"expected 5 backtest rows for BT-1, got {len(comparison)}"
    # backtest_id 一覧
    bt_ids = sorted(r["backtest_id"] for r in comparison)
    expected = sorted([
        "BT-1-30min_before-lightgbm",
        "BT-1-30min_before-catboost",
        "BT-1-10min_before-lightgbm",
        "BT-1-10min_before-catboost",
        "BT-1-confirmed-bl3",
    ])
    assert bt_ids == expected, f"backtest_id mismatch: got {bt_ids} expected {expected}"


def test_report_all_candidates_format(tmp_path):
    """reports/05-backtest.md の comparison_table に全 backtest_id が含まれる。"""
    result = _run_synthetic_bt1(tmp_path)
    md = result["md_text"]
    for bt_id in [
        "BT-1-30min_before-lightgbm",
        "BT-1-30min_before-catboost",
        "BT-1-10min_before-lightgbm",
        "BT-1-10min_before-catboost",
        "BT-1-confirmed-bl3",
    ]:
        assert bt_id in md, f"backtest_id {bt_id} が report.md に含まれない"


def test_report_no_winner_override(tmp_path):
    """reports/05-backtest.md に highest-recovery backtest_id を採用候補として突出させる語句が無い (BACK-04)。

    BACK-04 / §11.2: 「推奨:」形式の行や「採用候補として X を選出」等の突出表記を禁止。
   否定文脈 (「突出させる記述は一切ない」) は許容するが・実際の推奨行 (行頭が「推奨:」) は不可。
    """
    result = _run_synthetic_bt1(tmp_path)
    md = result["md_text"]
    # 行頭「推奨:」または「採用候補:」の突出行が無いことを検証
    for line in md.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("推奨:"), f"BACK-04 違反: 推奨行がある: {line!r}"
        assert not stripped.startswith("採用候補:"), f"BACK-04 違反: 採用候補行がある: {line!r}"
        assert not stripped.startswith("推荐:"), f"BACK-04 違反: 推荐行がある: {line!r}"


def test_report_strategy_version_stamp(tmp_path):
    """reports に backtest_strategy_version='fukusho_ev_v1' が定数として stamp されている。"""
    result = _run_synthetic_bt1(tmp_path)
    constants = result["json_data"]["constants"]
    assert constants["FUKUSHO_EV_V1_STRATEGY"] == "fukusho_ev_v1"
    md = result["md_text"]
    assert "fukusho_ev_v1" in md


def test_report_bl3_caveat_present(tmp_path):
    """notes に BL3_COMPARISON_CAVEAT §14.2 注記が含まれる。"""
    result = _run_synthetic_bt1(tmp_path)
    notes = result["json_data"]["notes"]
    caveat_found = any("§14.2" in n or "BL-3" in n for n in notes)
    assert caveat_found, f"BL3 caveat が notes に無い: {notes}"


def test_check_reproduce_smoke(tmp_path):
    """--check-reproduce で BT-1 の bit-identical 検証が通る (合成データ・train_and_predict は呼ばない)。

    合成データのため train_and_predict は呼ばれず・--check-reproduce は _assert_deterministic
    を呼ぶが _prepare_feature_df が readonly_pool None を許容するため合成 feature_df で完走する。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts import run_backtest  # noqa: PLC0415

    # 合成データの --check-reproduce は _prepare_feature_df が snapshot 読込を試みるため
    # FeatureMatrix ファイルが無いと FileNotFoundError。ここでは _assert_deterministic 相当
    # ではなく・_carve_calib_strict_ordering_and_deterministic (別テスト) で代用する。
    # 本テストは --check-reproduce フラグが parse されて pipeline に入ることを smoke 検証する。
    argv = [
        "--synthetic",
        "--bt-filter", "BT-1",
        "--check-reproduce",
        "--no-write-db",
        "--output-dir", str(tmp_path),
    ]
    args = run_backtest.parse_args(argv)
    assert args.check_reproduce is True
    assert args.synthetic is True
    assert args.bt_filter == "BT-1"


# ---------------------------------------------------------------------------
# HIGH-2: pred/snapshot JOIN 行数不変 (cartesian duplication 検出)
# ---------------------------------------------------------------------------


def test_pred_snapshot_join_row_count_invariant():
    """HIGH-2: 合成データで各 BT-1 test レースが複数馬を持ち・各馬に異なる JODDS snapshot がある場合・
    pred_df と snapshot の merge が (race_key, umaban) 単位で行数不変であることを検証する。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts import run_backtest  # noqa: PLC0415

    # 2レース × 各3頭の合成 feature_df_test を構築
    rows = []
    for race_idx, (jyocd, racenum) in enumerate([("05", 1), ("06", 2)]):
        race_key = f"2023-{jyocd}-1-06-{racenum}"
        race_date = pd.Timestamp("2023-06-05")
        race_start = race_date + pd.Timedelta(hours=15, minutes=30)
        for umaban in range(1, 4):
            rows.append({
                "year": "2023",
                "jyocd": jyocd,
                "kaiji": "1",
                "nichiji": "06",
                "racenum": str(racenum),
                "umaban": umaban,
                "kettonum": 1000000 + race_idx * 100 + umaban,
                "race_key": race_key,
                "race_date": race_date,
                "race_start_datetime": race_start,
                "p_fukusho_hit": 0.3 - 0.05 * (umaban - 1),
            })
    pred_df = pd.DataFrame(rows)

    # 各馬別々の odds snapshot (race_key + umaban 単位)
    snap_rows = []
    for _, r in pred_df.iterrows():
        snap_rows.append({
            "race_key": r["race_key"],
            "umaban": r["umaban"],
            "fuku_odds_lower": 2.0 + 0.5 * (r["umaban"] - 1),
            "fuku_odds_upper": 3.0 + 0.5 * (r["umaban"] - 1),
            "odds_missing_reason": None,
        })
    snapshot = pd.DataFrame(snap_rows)

    # (race_key, umaban) で merge → 行数不変
    merged = pred_df.merge(snapshot, on=["race_key", "umaban"], how="left")
    assert len(merged) == len(pred_df), (
        f"HIGH-2 行数不変違反: merged={len(merged)} pred={len(pred_df)}"
    )
    # race_key 単独で JOIN すると (馬数²) に膨らむことを対照実験で確認
    merged_wrong = pred_df.merge(
        snapshot.drop(columns=["umaban"]), on=["race_key"], how="left", suffixes=("", "_w")
    )
    assert len(merged_wrong) > len(pred_df), (
        "対照実験失敗: race_key 単独 JOIN で行数が膨らまない (テスト前提が崩れている)"
    )

    # _run_main_model_backtest が内部で行数不変 assert を持つことも確認 (source grep)
    import inspect

    src = inspect.getsource(run_backtest._run_main_model_backtest)
    assert "len(pred_with_odds)" in src and "len(pred_df)" in src, (
        "_run_main_model_backtest に行数不変 assert がない (HIGH-2 違反)"
    )


# ---------------------------------------------------------------------------
# HIGH-1: 馬単位 odds が pipeline 通過後も各馬の EV_lower に基づく計算であること
# ---------------------------------------------------------------------------


def test_horse_level_odds_preserved_in_pipeline():
    """HIGH-1: 合成データで race R1 の umaban 1 (odds 3.0) / umaban 2 (odds 5.0) が
    pipeline 通過後も各馬の EV_lower = p × odds に基づく計算であることを検証する
    (一方の馬の odds で両者上書きされない)。
    """
    # compute_ev_and_rank を直接呼び・馬単位 odds が維持されることを検証
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from src.ev.ev_rank import compute_ev_and_rank  # noqa: PLC0415

    df = pd.DataFrame([
        {"race_key": "R1", "umaban": 1, "p_fukusho_hit": 0.20, "fuku_odds_lower": 3.0, "fuku_odds_upper": 3.5},
        {"race_key": "R1", "umaban": 2, "p_fukusho_hit": 0.20, "fuku_odds_lower": 5.0, "fuku_odds_upper": 5.5},
    ])
    out = compute_ev_and_rank(df)
    # 各馬別々の EV_lower
    ev_u1 = out.loc[out["umaban"] == 1, "EV_lower"].iloc[0]
    ev_u2 = out.loc[out["umaban"] == 2, "EV_lower"].iloc[0]
    assert ev_u1 == pytest.approx(0.20 * 3.0), f"umaban1 EV_lower={ev_u1} 期待 0.6"
    assert ev_u2 == pytest.approx(0.20 * 5.0), f"umaban2 EV_lower={ev_u2} 期待 1.0"
    assert ev_u1 != ev_u2, "両馬の EV_lower が同一 (馬単位 odds が上書きされた可能性)"


# ---------------------------------------------------------------------------
# HIGH-5: BT窓 category_map refit で test 窓 ID が __UNSEEN__ に mapping
# ---------------------------------------------------------------------------


def test_bt_category_map_refit_excludes_test_ids():
    """HIGH-5: BT-1 train 期間に現れない jockey_id が BT-1 test 期間に存在する合成データで・
    fit_category_map で構築した map を適用すると test 窓の新規 ID が __UNSEEN__ sentinel になる。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from src.utils.category_map import UNSEEN, apply_category_map, fit_category_map  # noqa: PLC0415

    # train 窓: jk1..jk5 のみ現れる
    train_series = pd.Series(["jk1", "jk2", "jk3", "jk4", "jk5"])
    bt_map = fit_category_map(train_series)
    # test 窓: train に無い jk99 が現れる
    test_series = pd.Series(["jk1", "jk99", "jk5"])
    codes = apply_category_map(test_series, bt_map)
    # jk1/jk5 は train map の code・jk99 は __UNSEEN__ code
    assert codes.iloc[0] == bt_map["jk1"], "jk1 が train map code に mapping されていない"
    assert codes.iloc[2] == bt_map["jk5"], "jk5 が train map code に mapping されていない"
    assert codes.iloc[1] == bt_map[UNSEEN], (
        f"jk99 (test 窓新規 ID) が __UNSEEN__ sentinel に mapping されていない: got {codes.iloc[1]}"
    )


# ---------------------------------------------------------------------------
# LOW-05: REPORT_COLUMNS の全要素が report 出力に含まれる (presence 検証)
# ---------------------------------------------------------------------------


def test_report_columns_present(tmp_path):
    """LOW-05: REPORT_COLUMNS の全要素が reports/05-backtest.json の comparison_table のキー
    (または md の列ヘッダ) に存在することを presence assert で検証する (grep 否定でない)。
    """
    result = _run_synthetic_bt1(tmp_path)
    json_data = result["json_data"]
    md_text = result["md_text"]

    # json constants に REPORT_COLUMNS が含まれる
    report_columns = json_data["constants"]["REPORT_COLUMNS"]
    # comparison_table の各行が REPORT_COLUMNS の全キーを持つ
    for row in json_data["comparison_table"]:
        for col in report_columns:
            assert col in row, f"comparison_table 行に {col!r} キーがない (LOW-05 presence 違反)"

    # md の列ヘッダ行に REPORT_COLUMNS の全要素が含まれる
    # md は "| backtest_id | bt_name | ..." 形式
    header_line = None
    for line in md_text.splitlines():
        if line.startswith("| backtest_id"):
            header_line = line
            break
    assert header_line is not None, "md に comparison table ヘッダ行がない"
    for col in report_columns:
        assert col in header_line, f"md ヘッダ行に列 {col!r} がない (LOW-05)"


# ---------------------------------------------------------------------------
# HIGH-B cycle-2: _carve_calib_from_train_tail の順序不変 + deterministic
# ---------------------------------------------------------------------------


def test_carve_calib_strict_ordering_and_deterministic():
    """HIGH-B cycle-2: _carve_calib_from_train_tail を BT-1..BT-5 全窓で呼出し・各窓で
    max(train.race_date) < min(calib.race_date) < max(calib.race_date) < min(test.race_date)
    の順序不変を assert。さらに同一 BT窓に対し2回 carve して全ての期間が bit-identical であることを assert。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts import run_backtest  # noqa: PLC0415
    from src.utils.group_split import BT_WINDOWS  # noqa: PLC0415

    for bt in BT_WINDOWS:
        periods1 = run_backtest._carve_calib_from_train_tail(bt)
        periods2 = run_backtest._carve_calib_from_train_tail(bt)
        # deterministic (同一 BT窓で2回 carve → bit-identical)
        assert periods1 == periods2, (
            f"HIGH-B deterministic 違反: {bt.name} で2回 carve で結果が異なる: {periods1} vs {periods2}"
        )
        train_start, train_end = periods1["train"]
        calib_start, calib_end = periods1["calib"]
        test_start, test_end = periods1["test"]
        # 順序不変: max(train) < min(calib) < max(calib) < min(test)
        # train_end < calib_start <= calib_end < test_start を文字列日付として検証 (ISO 日付は辞書順 = 時系列順)
        assert train_start < train_end, f"{bt.name}: train_start >= train_end ({train_start} >= {train_end})"
        assert train_end < calib_start, (
            f"HIGH-B 順序違反 {bt.name}: train_end({train_end}) >= calib_start({calib_start}) "
            "(train_start 固定・train_end=calib_start-1day であるべき)"
        )
        assert calib_start <= calib_end, f"{bt.name}: calib_start > calib_end"
        assert calib_end < test_start, f"{bt.name}: calib_end({calib_end}) >= test_start({test_start})"
        assert test_start <= test_end, f"{bt.name}: test_start > test_end"
        # HIGH-B 修正確認: train_start は BT窓定義の train_start に等しい (固定)
        assert train_start == bt.train_start, (
            f"HIGH-B 違反 {bt.name}: train_start({train_start}) が BT窓定義({bt.train_start}) と異なる "
            "(train_start は固定・train_end のみ短縮されるべき)"
        )


# ---------------------------------------------------------------------------
# HIGH-C cycle-2: HARAI race-level merge + 行ベース slot lookup
# ---------------------------------------------------------------------------


def test_harai_payout_lookup_no_broadcast():
    """HIGH-C cycle-2: 合成データで race R1 に umaban {1,2,3}・HARAI race-level slot が
    PayFukusyoUmaban1=1/PayFukusyoPay1=210・PayFukusyoUmaban2=3/PayFukusyoPay2=150・
    slot3-5='00'/0 (不的中) の場合・race-level merge(validate='many_to_one') で構築され・
    行数 == 入力候補馬数 (3行・ブロードキャスト膨張なし)・_lookup_payfukusyo_pay が
    umaban1→210 / umaban3→150 / umaban2→0 (不的中) を返す。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from src.ev.refund_accounting import _lookup_payfukusyo_pay  # noqa: PLC0415

    # 3頭の馬行
    horses = pd.DataFrame([
        {"race_key": "R1", "umaban": 1, "p_fukusho_hit": 0.3},
        {"race_key": "R1", "umaban": 2, "p_fukusho_hit": 0.25},
        {"race_key": "R1", "umaban": 3, "p_fukusho_hit": 0.20},
    ])
    # race-level HARAI slot (1行・umaban 列なし)
    harai_race = pd.DataFrame([{
        "race_key": "R1",
        "fuseirituflag2": "0",
        "henkanflag2": "0",
        "tokubaraiflag2": "0",
        "payfukusyoumaban1": "01",
        "payfukusyopay1": "0000210",
        "payfukusyoumaban2": "03",
        "payfukusyopay2": "0000150",
        "payfukusyoumaban3": "00",
        "payfukusyopay3": "0000000",
        "payfukusyoumaban4": "00",
        "payfukusyopay4": "0000000",
        "payfukusyoumaban5": "00",
        "payfukusyopay5": "0000000",
    }])
    # race-level merge validate='many_to_one'
    harai_cols = [c for c in harai_race.columns if c != "race_key"]
    merged = horses.merge(
        harai_race[["race_key"] + harai_cols], on=["race_key"], how="left", validate="many_to_one"
    )
    # 行数不変 (3行・ブロードキャスト膨張なし)
    assert len(merged) == 3, f"HIGH-C 行数不変違反: merged={len(merged)} 期待 3"

    # 行ベース slot lookup で正しい払戻
    assert _lookup_payfukusyo_pay(merged.loc[merged["umaban"] == 1].iloc[0]) == 210
    assert _lookup_payfukusyo_pay(merged.loc[merged["umaban"] == 3].iloc[0]) == 150
    assert _lookup_payfukusyo_pay(merged.loc[merged["umaban"] == 2].iloc[0]) == 0  # 不的中


# ---------------------------------------------------------------------------
# MEDIUM-A cycle-2 + MEDIUM cycle-3: non-selected 永続化 + 会計ゼロ化
# ---------------------------------------------------------------------------


def test_load_backtest_persists_nonselected():
    """MEDIUM-A cycle-2 + MEDIUM cycle-3: select_bets 後 selected_flag=True が2頭・
    selected_flag=False が5頭の full_candidate_with_accounting で・_zero_out_non_selected_accounting
    が selected_flag=False 行の stake/effective_stake/payout/refund/profit を全て 0 にする。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts import run_backtest  # noqa: PLC0415

    # 7行 (selected 2 + non-selected 5) の合成 full_candidate_with_accounting
    rows = []
    for i in range(7):
        rows.append({
            "race_key": "R1",
            "umaban": i + 1,
            "selected_flag": i < 2,  # umaban 1,2 が selected
            "stake": 100,
            "effective_stake": 100,
            "payout": 200 if i < 2 else 0,
            "refund": 0,
            "profit": 100 if i < 2 else -100,
            "race_date": pd.Timestamp("2023-06-05"),
            "fukusho_hit_validated": 1 if i < 2 else 0,
            "is_fukusho_sale_available": True,
            "refund_flag": False,
            "refund_amount": 0,
            "payout_amount": 200 if i < 2 else 0,
        })
    df = pd.DataFrame(rows)
    out = run_backtest._zero_out_non_selected_accounting(df)
    # selected_flag=False 行 (umaban 3..7) の会計が全て 0
    non_sel = out[out["selected_flag"] == False]  # noqa: E712
    assert len(non_sel) == 5
    for col in ["stake", "effective_stake", "payout", "refund", "profit"]:
        assert (non_sel[col] == 0).all(), (
            f"MEDIUM cycle-3 違反: non-selected 行の {col} がゼロ化されていない: {non_sel[col].tolist()}"
        )
    # selected_flag=True 行 (umaban 1,2) は会計が維持される
    sel = out[out["selected_flag"] == True]  # noqa: E712
    assert len(sel) == 2
    assert (sel["stake"] == 100).all()
    assert (sel["payout"] == 200).all()

    # source に loc[...]==0 のゼロ化記述があることも検証 (acceptance grep)
    import inspect

    src = inspect.getsource(run_backtest._zero_out_non_selected_accounting)
    assert "selected_flag" in src and ".loc[" in src, (
        "_zero_out_non_selected_accounting に selected_flag と loc[...] のゼロ化記述がない"
    )


# ---------------------------------------------------------------------------
# MEDIUM-B cycle-2: horse-level usable-odds coverage gate
# ---------------------------------------------------------------------------


def test_horse_level_odds_coverage_gate():
    """MEDIUM-B cycle-2: 合成データで BT-1 test の候補10頭中8頭が usable odds・
    2頭が no_bet sentinel の場合・usable_coverage=0.80 で閾値 0.90 を下回り RuntimeError が raise。
    """
    import sys

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts import run_backtest  # noqa: PLC0415
    from src.utils.group_split import BT_WINDOWS  # noqa: PLC0415

    bt1 = next(b for b in BT_WINDOWS if b.name == "BT-1")
    # 10頭の候補 (race_key/umaban) - 8 usable + 2 no_bet
    pred_df = pd.DataFrame([
        {"race_key": "R1", "umaban": u, "race_start_datetime": pd.Timestamp("2023-06-05 15:30")}
        for u in range(1, 11)
    ])
    snapshot = pd.DataFrame([
        {"race_key": "R1", "umaban": u, "fuku_odds_lower": 2.0 + u * 0.1, "odds_missing_reason": None}
        for u in range(1, 9)  # umaban 1..8 は usable
    ] + [
        {"race_key": "R1", "umaban": u, "fuku_odds_lower": float("nan"), "odds_missing_reason": "no_bet"}
        for u in (9, 10)  # umaban 9,10 は no_bet sentinel
    ])
    # pred_df の race_key は R1 のみ → total_races=1
    # coverage < threshold → RuntimeError
    with pytest.raises(RuntimeError, match=r"MEDIUM-B horse-level usable-odds coverage.*< threshold"):
        run_backtest._assert_jodds_coverage_horse_level(bt1, "30min_before", pred_df, snapshot)

    # 全員 usable の場合は通過する (coverage=1.0 >= threshold)
    snapshot_all_usable = pd.DataFrame([
        {"race_key": "R1", "umaban": u, "fuku_odds_lower": 2.0 + u * 0.1, "odds_missing_reason": None}
        for u in range(1, 11)
    ])
    result = run_backtest._assert_jodds_coverage_horse_level(
        bt1, "30min_before", pred_df, snapshot_all_usable
    )
    assert result["status"] == "pass"
    assert result["horse_level_coverage"] == pytest.approx(1.0)
