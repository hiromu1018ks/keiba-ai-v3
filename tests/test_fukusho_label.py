"""LABEL-01/02/04 unit test for src.etl.fukusho_label (Plan 02-02, TDD RED phase).

RESEARCH Validation Architecture 準拠・mock cursor / 合成 DataFrame で DB 不要・
``@pytest.mark.requires_db`` は integration test のみ（本ファイルは全テスト unit・未使用）。

REVIEWS 対応:
  - HIGH #1 (inferred conflation): test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status
  - HIGH #4 (race_cancelled rows dropped): test_race_cancelled_all_unresolved / test_select_se_state_includes_datakubun_9
  - HIGH #5 (brittle markers): test_canonicalize_markers_raw_string_form / _numeric_cast_form
  - HIGH #6 (dead_loss reason precision): test_dead_loss_in_obstacle_race_excluded_for_obstacle_reason
  - MEDIUM (§7.2 未勝利 precision): test_is_model_eligible_maiden_syubetucd_included
  - NEW HIGH #2 (timediff merge row multiplication): test_select_se_state_no_row_multiplication_on_timediff_merge
  - NEW HIGH #3 (missing time misclassified): test_canonicalize_markers_missing_time

TDD note: このファイルが作成される時点（Plan 02-02）では src/etl/fukusho_label.py
（Plan 02-03）が未実装のため、全テストが ImportError / AttributeError / ModuleNotFoundError
で fail する状態（RED）が正常。Plan 02-03 の GREEN 実装がこれらのテストを通す。
"""

from __future__ import annotations

import inspect
import re

import numpy as np
import pandas as pd
import pytest

# TDD RED: src.etl.fukusho_label は Plan 02-03 で実装される。
# モジュールレベル import すると collection error でテスト名が列挙されず
# RED の検証（pytest --collect-only でテスト名が出る）ができなくなるため、
# 各テスト内で遅延 import して AttributeError/ImportError で fail させる。
# Plan 02-03 GREEN で src.etl.fukusho_label が存在すれば全テスト通過可能。


def _get_fukusho_label_module():
    """遅延 import helper。Plan 02-03 GREEN まで ModuleNotFoundError で fail (RED)。"""
    from src.etl import fukusho_label

    return fukusho_label


# ---------------------------------------------------------------------------
# Helpers: synthetic n_harai (HR) / n_uma_race (SE) / normalized.n_race rows
# 実DBに依存せず deterministic にラベル計算ロジックを検証するための synthetic builder。
# カラム名は Pitfall 1 の実カラム名（timediff / bataijyu）を厳格に使用。
# ---------------------------------------------------------------------------


def _build_hr_row(**overrides) -> dict:
    """n_harai 1レース分の合成行。デフォルトは8頭・月曜確定・複勝払戻3頭。"""
    row = {
        "year": "2023",
        "monthday": "0101",
        "jyocd": "05",
        "kaiji": "01",
        "nichiji": "01",
        "racenum": "01",
        "datakubun": "2",          # 月曜確定
        "torokutosu": "8",         # 登録頭数（sales_start_entry_count 代理値）
        "syussotosu": "8",         # 出走頭数
        "fuseirituflag2": "0",     # 複勝成立
        "tokubaraiflag2": "0",     # 複勝特払 無し
        "henkanflag2": "0",        # 複勝返還 無し
        "payfukusyoumaban1": "01",
        "payfukusyoumaban2": "02",
        "payfukusyoumaban3": "03",
        "payfukusyoumaban4": "",
        "payfukusyoumaban5": "",
    }
    row.update(overrides)
    return row


def _build_se_row(umaban: int, **overrides) -> dict:
    """n_uma_race 1馬行分。デフォルトは正常出走馬。"""
    row = {
        "year": "2023",
        "monthday": "0101",
        "jyocd": "05",
        "kaiji": "01",
        "nichiji": "01",
        "racenum": "01",
        "umaban": f"{umaban:02d}",
        "kettonum": f"{umaban:03d}",
        "kakuteijyuni": f"{umaban:02d}",   # 着順 = umaban と同順（1..N）
        "bataijyu": "057",                 # 馬体重正常
        "harontimel3": "1.0",              # ハロンタイム正常
        "timediff": "0",                   # TimeDIFN 正常（実カラム名は timediff）
        "time": "90.0",                    # 走破タイム有り（発走後完走）
        "datakubun": "7",                  # 月曜確定 SE
        "dochakukubun": "0",
        "dochakutosu": "0",
    }
    row.update(overrides)
    return row


def _build_label_input_df(
    n_horses: int,
    hr_overrides: dict | None = None,
    se_overrides: dict | None = None,
    syubetucd: str = "00",
    class_level_numeric: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(hr_df, se_df, race_df) を返す合成ビルダー。

    - hr_df : n_harai 1レース分（hr_overrides で上書き）
    - se_df : n_horses 行の SE（各馬 umaban=1..N・se_overrides は全馬に適用）
    - race_df: normalized.n_race 相当 1行（syubetucd / class_level_numeric 含む）
    """
    hr_row = _build_hr_row(**(hr_overrides or {}))
    # 出走頭数・払戻対象数は hr_overrides で明示的に変えない限り n_horses に合わせる
    if hr_overrides is None or "torokutosu" not in hr_overrides:
        hr_row["torokutosu"] = f"{n_horses}"
    if hr_overrides is None or "syussotosu" not in hr_overrides:
        hr_row["syussotosu"] = f"{n_horses}"
    hr_df = pd.DataFrame([hr_row])

    se_rows = []
    for u in range(1, n_horses + 1):
        se_rows.append(_build_se_row(u, **(se_overrides or {})))
    se_df = pd.DataFrame(se_rows)

    race_df = pd.DataFrame(
        [
            {
                "year": "2023",
                "monthday": "0101",
                "jyocd": "05",
                "kaiji": "01",
                "nichiji": "01",
                "racenum": "01",
                "syubetucd": syubetucd,
                "class_level_numeric": class_level_numeric,
            }
        ]
    )
    return hr_df, se_df, race_df


# ---------------------------------------------------------------------------
# LABEL_SPEC: テスト内で sentinel / 境界値を参照するための読込（Plan 02-01 作成済み）
# ---------------------------------------------------------------------------


def _load_label_spec() -> dict:
    """src/config/label_spec.yaml を読込（Plan 02-01 で作成済み・D-07 Git 管理）。"""
    import yaml  # noqa: PLC0415

    with open("src/config/label_spec.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ===========================================================================
# Task 1: LABEL-01 / LABEL-02 unit tests
# ===========================================================================


def test_fukusho_module_imports() -> None:
    """src.etl.fukusho_label から公開 API が import 可能（Plan 03 GREEN 前提）。"""
    fukusho_label = _get_fukusho_label_module()

    assert callable(fukusho_label.compute_fukusho_labels)
    assert callable(fukusho_label.classify_status)
    assert callable(fukusho_label.compute_is_model_eligible)
    assert callable(fukusho_label._canonicalize_markers)
    assert callable(fukusho_label.run_label_etl)


def test_raw_vs_validated_basic_8_horses() -> None:
    """8頭レース・KakuteiJyuni=1,2,3 が raw 勝利・PayFukusyoUmaban1..3 と整合する検証。"""
    hr_df, se_df, race_df = _build_label_input_df(8)
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # LABEL-01 raw layer (KakuteiJyuni-based)
    assert (out.loc[out["umaban"].isin(["01", "02", "03"]), "fukusho_hit_raw"] == 1).all()
    assert (out.loc[out["umaban"].isin(["04", "05", "06", "07", "08"]), "fukusho_hit_raw"] == 0).all()
    # LABEL-01 validated layer (PayFukusyoUmaban1..3='01','02','03' と整合)
    assert (out.loc[out["umaban"].isin(["01", "02", "03"]), "fukusho_hit_validated"] == 1).all()
    # 8頭なので payout_places=3
    assert (out["fukusho_payout_places"] == 3).all()
    # torokutosu=8 >= 5・fuseirituflag2='0' → 複勝発売あり
    assert (out["is_fukusho_sale_available"] == True).all()  # noqa: E712


def test_raw_vs_validated_basic_6_horses() -> None:
    """6頭レース・payout_places=2・KakuteiJyuni=1,2 が raw 勝利・PayFukusyoUmaban1..2 と整合。"""
    hr_df, se_df, race_df = _build_label_input_df(
        6, hr_overrides={"torokutosu": "6", "syussotosu": "6", "payfukusyoumaban3": ""}
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out.loc[out["umaban"].isin(["01", "02"]), "fukusho_hit_raw"] == 1).all()
    assert (out.loc[out["umaban"].isin(["03", "04", "05", "06"]), "fukusho_hit_raw"] == 0).all()
    assert (out["fukusho_payout_places"] == 2).all()


def test_drift_is_dead_heat_only() -> None:
    """drift (raw vs validated 不一致) は全て dead_heat status に分類される検証。

    シナリオ: 8頭レース・PayFukusyoUmaban1..4='01','02','03','04'（同着で4頭・理論値3超過）。
    SE 側 KakuteiJyuni=1,2,3 の3頭のみ raw=1 だが、validated は4頭=1。
    umaban=4 の馬が drift（raw=0, valid=1）。全馬行が 'dead_heat' status に分類される。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "04",
            "payfukusyoumaban5": "",
        },
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # drift 行は umaban=4 の1行のみ（raw=0, validated=1）
    drift_rows = out[out["fukusho_hit_raw"] != out["fukusho_hit_validated"]]
    assert len(drift_rows) >= 1
    # drift が発生した場合、そのレースの全馬行は dead_heat status
    assert (out["label_validation_status"] == "dead_heat").all()


def test_sales_start_entry_count_proxy_and_source_confidence_separated_from_status() -> None:
    """REVIEWS HIGH #1: sales_start_entry_count_confidence と label_validation_status の分離。

    torokutosu='12' で HR DataKubun='2' のレース:
      - sales_start_entry_count == 12
      - sales_start_entry_count_source == 'torokutosu_proxy'
      - sales_start_entry_count_confidence == 'inferred' （独立列）
      - label_validation_status == 'validated'            （HR DataKubun='2'）
    両者が独立した列に格納されることを証明（conflation 回避）。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8, hr_overrides={"torokutosu": "12", "datakubun": "2"}
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # sales_start_entry_count 系カラムが独立列として存在
    assert "sales_start_entry_count" in out.columns
    assert "sales_start_entry_count_source" in out.columns
    assert "sales_start_entry_count_confidence" in out.columns
    assert "label_validation_status" in out.columns

    # 全行で proxy 値と confidence を保持
    assert (out["sales_start_entry_count"] == 12).all()
    assert (out["sales_start_entry_count_source"] == "torokutosu_proxy").all()
    assert (out["sales_start_entry_count_confidence"] == "inferred").all()
    # label_validation_status は inferred ではなく 'validated'（HR DataKubun='2'）
    assert (out["label_validation_status"] == "validated").all()
    # conflation 検知: confidence が inferred でも status は inferred ではない
    assert not (out["label_validation_status"] == "inferred").any()


def test_unresolved_triggers_hr_missing() -> None:
    """HR レコード欠損（torokutosu IS NULL）の馬行は unresolved / is_model_eligible=False。"""
    hr_df = pd.DataFrame(columns=[
        "year", "monthday", "jyocd", "kaiji", "nichiji", "racenum", "datakubun",
        "torokutosu", "syussotosu", "fuseirituflag2", "tokubaraiflag2", "henkanflag2",
        "payfukusyoumaban1", "payfukusyoumaban2", "payfukusyoumaban3",
        "payfukusyoumaban4", "payfukusyoumaban5",
    ])
    _, se_df, race_df = _build_label_input_df(8)
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["label_validation_status"] == "unresolved").all()
    assert (out["is_model_eligible"] == False).all()  # noqa: E712


def test_no_fukusho_sale_under_5_horses() -> None:
    """TorokuTosu='4' のレースは複勝発売なし・payout_places=0・不適格（no_fukusho_sale）。"""
    hr_df, se_df, race_df = _build_label_input_df(
        4,
        hr_overrides={"torokutosu": "4", "payfukusyoumaban1": "00",
                      "payfukusyoumaban2": "", "payfukusyoumaban3": ""},
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["is_fukusho_sale_available"] == False).all()  # noqa: E712
    assert (out["fukusho_payout_places"] == 0).all()
    assert (out["is_model_eligible"] == False).all()  # noqa: E712
    assert (out["ineligibility_reason"] == "no_fukusho_sale").all()


def test_payout_places_uses_syussotosu_not_torokutosu() -> None:
    """WR-04 (iteration 2): 払戻対象頭数は実際出走頭数（syussotosu）ベース。

    登録8頭（torokutosu=8）でも取消1頭で実7頭出走（syussotosu=7）なら **2頭払い**
    （2着まで）。旧 Pitfall 3（torokutosu ベース・3頭払い）は実DB観測で誤りと判明し撤回。
    本テストは7件の validated drift のうち5件が torokutosu ベース誤判定であった根本原因
    （CR-01 を revert した原因）を回帰検出する。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8, hr_overrides={"torokutosu": "8", "syussotosu": "7"}
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # WR-04: syussotosu=7 → 2頭払い（torokutosu=8 だが実際出走は7頭）
    assert (out["fukusho_payout_places"] == 2).all(), (
        "WR-04: torokutosu=8, syussotosu=7 は 2頭払い（2着まで）でなければならない。"
        "torokutosu ベースの3頭払い計算は7件 validated drift のうち5件の根本原因。"
    )


def test_payout_places_scratch_race_3rd_place_excluded() -> None:
    """WR-04 (iteration 2): 取消レース（torokutosu=8, syussotosu=7）で 3着馬の raw=0。

    2頭払いレースでは3着馬（kakuteijyuni='03'）は払戻対象外。torokutosu ベース3頭払い
    計算だと誤って raw=1 になり、HR（正しく2頭払い）の3着馬番='00' と食い違って
    validated drift になる（実DBの5件ドリフトの再現）。syussotosu ベースで raw=0 となる
    ことを検証する。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "torokutosu": "8",
            "syussotosu": "7",
            # HR は2頭払いとして記録（3着 slot='00' = 対象外）
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "00",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # payout_places = 2（syussotosu=7）
    assert (out["fukusho_payout_places"] == 2).all()
    # 3着馬（kakuteijyuni='03' → umaban='03'）は払戻対象外・raw=0・validated=0
    row3 = out[out["umaban"] == "03"].iloc[0]
    assert row3["fukusho_hit_raw"] == 0, (
        "WR-04: 2頭払いレース（syussotosu=7）では3着馬は払戻対象外・raw=0 でなければならない。"
        "torokutosu ベース3頭払いだと raw=1 になり HR と食い違う（実DB5件ドリフトの再現）。"
    )
    assert row3["fukusho_hit_validated"] == 0  # HR slot3='00' → payout set に含まれない
    # raw と validated が一致（drift 無し）・CR-01 が検知すべきでなかった誤検知の回帰
    drift_rows = out[out["fukusho_hit_raw"] != out["fukusho_hit_validated"]]
    assert len(drift_rows) == 0, (
        "WR-04: 取消レース（2頭払い正しく計算）では raw/validated drift が発生しない。"
        f"drift 行: {drift_rows[['umaban','fukusho_hit_raw','fukusho_hit_validated']].to_dict('records')}"
    )


def test_payout_places_normal_race_8_starters_3_places_regression() -> None:
    """WR-04 regression: torokutosu=8, syussotosu=8 の通常レースは3頭払いのまま。

    syussotosu ベースに変更しても、取消の無い通常レース（torokutosu == syussotosu）
    の payout_places は従来通り3（8頭以上）であることを検証する。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8, hr_overrides={"torokutosu": "8", "syussotosu": "8"}
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # 取消なし・torokutosu=syussotosu=8 → 3頭払い
    assert (out["fukusho_payout_places"] == 3).all()
    # 1-3着馬は raw=1
    assert (out.loc[out["umaban"].isin(["01", "02", "03"]), "fukusho_hit_raw"] == 1).all()
    assert (out.loc[out["umaban"].isin(["04", "05"]), "fukusho_hit_raw"] == 0).all()


def test_payout_places_syussotosu_missing_returns_no_sale() -> None:
    """WR-04 (iteration 2): syussotosu 欠損時は payout_places=0（no_sale）。

    D-13 silent fallback 禁止・安全側。_payout_places の先頭の _is_na ガードで処理される
    ことを検証する。torokutosu が有効でも syussotosu が欠損なら境界は確定できないため
    no_sale に隔離される（学習除外）。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    no_sale = int(spec["payout_places_rules"]["no_sale_marker_value"])

    # syussotosu を欠損（pd.NA / None / 空文字 / 英字混じり）にした4パターン
    abnormal_values = [
        pd.NA,
        None,
        "",
        "abc",
    ]
    for bad in abnormal_values:
        hr_df, se_df, race_df = _build_label_input_df(
            8, hr_overrides={"torokutosu": "8", "syussotosu": bad}
        )
        out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
        assert (out["fukusho_payout_places"] == no_sale).all(), (
            f"WR-04: syussotosu={bad!r} のとき fukusho_payout_places が no_sale({no_sale}) "
            f"でない行がある: {out['fukusho_payout_places'].tolist()}"
        )


def test_payout_places_and_is_dh_handle_pd_na_and_abnormal_values() -> None:
    """CR-03 regression: syussotosu が pd.NA / np.float64(nan) / 空文字 / 英字混じりの場合に
    TypeError を起こさず no_sale に正規化されること。

    WR-04 (iteration 2) で ``fukusho_payout_places`` の計算ベースが torokutosu から
    syussotosu に変更されたため、本 regression も異常値を syussotosu に駆動させる。

    _payout_places の int() 変換で pd.NA が TypeError になる経路（Int64 nullable dtype
    等で発生し得る）と異常 varchar 値（pd.to_numeric → nan）の両方をガードする。
    仕様境界（payout_places_rules）は変更しない。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    no_sale = int(spec["payout_places_rules"]["no_sale_marker_value"])

    # 4パターンの異常 syussotosu 値を1レースずつ作り、それぞれの fukusho_payout_places
    # が no_sale になることを検証する。SE 側は正常马（8頭）で固定し HR 側の syussotosu
    # のみ変える（torokutosu は正常値 '8' に固定）。
    abnormal_values = [
        pd.NA,                  # pandas NA・str(pd.NA)='<NA>' で TypeError 経路
        np.float64("nan"),      # numpy nan・_is_na で捕捉される経路
        "",                     # 空文字・pd.to_numeric(errors='coerce') → nan
        "abc",                  # 英字混じり・pd.to_numeric(errors='coerce') → nan
    ]
    for bad in abnormal_values:
        hr_df, se_df, race_df = _build_label_input_df(
            8, hr_overrides={"torokutosu": "8", "syussotosu": bad}
        )
        # pd.NA は dict 経由で DataFrame に入ると object dtype になる。
        # compute_fukusho_labels 内の pd.to_numeric(errors='coerce') が nan を返し、
        # _payout_places の _is_na 分岐 / try-except 分岐で no_sale になる。
        out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
        assert (out["fukusho_payout_places"] == no_sale).all(), (
            f"CR-03: syussotosu={bad!r} で fukusho_payout_places が no_sale({no_sale}) "
            f"でない行がある: {out['fukusho_payout_places'].tolist()}"
        )
        # is_dead_heat も TypeError を起こさず False になること（payout_places <= 0 で早期 False）
        assert (out["is_dead_heat"] == False).all()  # noqa: E712


def test_is_dh_handles_hr_missing_payout_count_nan() -> None:
    """CR-03 regression: HR merge が left join で HR 欠損行の payout_count が NaN に
    なる経路で _is_dh が TypeError を起こさず False を返すこと。

    SE 行が存在するが HR 側にレースが無い（unresolved）ケースを模倣し、
    payout_count が NaN でも is_dead_heat=False になることを検証する。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    # HR を空（payout_count が NaN になる）にするため空 DataFrame を渡す
    # （test_unresolved_triggers_hr_missing と同等のシナリオ）。
    se_df = pd.DataFrame([_build_se_row(u) for u in range(1, 9)])
    # HR 列だけ定義された空 DataFrame（compute_fukusho_labels が merge で left join し、
    # HR 系列が NaN になる）
    hr_df = pd.DataFrame(
        columns=[
            "year", "monthday", "jyocd", "kaiji", "nichiji", "racenum", "datakubun",
            "torokutosu", "syussotosu", "fuseirituflag2", "tokubaraiflag2", "henkanflag2",
            "payfukusyoumaban1", "payfukusyoumaban2", "payfukusyoumaban3",
            "payfukusyoumaban4", "payfukusyoumaban5",
        ]
    )
    race_df = pd.DataFrame(
        [
            {
                "year": "2023", "jyocd": "05", "kaiji": "01", "nichiji": "01",
                "racenum": "01", "syubetucd": "00", "class_level_numeric": 2,
            }
        ]
    )
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # HR 欠損行では is_dead_heat が TypeError で crash せず False になる
    assert "is_dead_heat" in out.columns
    assert (out["is_dead_heat"] == False).all()  # noqa: E712


def test_canonicalize_markers_raw_string_form() -> None:
    """REVIEWS HIGH #5: raw varchar 表現で marker 判定が正しいこと。

    行A: harontimel3='999.0' / timediff='9999' / time='9990.0' / bataijyu='057' / datakubun='7'
          → 競走中止（is_dead_loss=True）
    行B: harontimel3='1.0' / timediff='0' / time='90.0' / bataijyu='000' / datakubun='7'
          → 出走取消（is_scratch_cancel=True）
    行C: harontimel3='1.0' / timediff='0' / time='90.0' / bataijyu='057' / datakubun='9'
          → レース全体中止（is_race_cancelled=True）
    """
    spec = _load_label_spec()
    rows = [
        {"harontimel3": "999.0", "timediff": "9999", "time": "9990.0",
         "bataijyu": "057", "datakubun": "7"},   # A: dead_loss
        {"harontimel3": "1.0", "timediff": "0", "time": "90.0",
         "bataijyu": "000", "datakubun": "7"},   # B: scratch_cancel
        {"harontimel3": "1.0", "timediff": "0", "time": "90.0",
         "bataijyu": "057", "datakubun": "9"},   # C: race_cancelled
    ]
    df = pd.DataFrame(rows)
    mod = _get_fukusho_label_module()
    out = mod._canonicalize_markers(df, spec)

    assert out.loc[0, "is_dead_loss"] == True      # noqa: E712
    assert out.loc[0, "is_scratch_cancel"] == False  # noqa: E712
    assert out.loc[0, "is_race_cancelled"] == False  # noqa: E712

    assert out.loc[1, "is_dead_loss"] == False     # noqa: E712
    assert out.loc[1, "is_scratch_cancel"] == True   # noqa: E712
    assert out.loc[1, "is_race_cancelled"] == False  # noqa: E712

    assert out.loc[2, "is_dead_loss"] == False     # noqa: E712
    assert out.loc[2, "is_scratch_cancel"] == False  # noqa: E712
    assert out.loc[2, "is_race_cancelled"] == True   # noqa: E712


def test_canonicalize_markers_numeric_cast_form() -> None:
    """REVIEWS HIGH #5: pd.to_numeric で数値キャスト後も同一判定。

    raw 文字列表現（test_canonicalize_markers_raw_string_form）と同一シナリオで、
    harontimel3=999.0 (float) / timediff=9999 (int) / time=9990.0 (float) /
    bataijyu=57 (int) / datakubun='7' (str のまま) でも同一結果。
    sentinel 集合ベース判定の核心。
    """
    spec = _load_label_spec()
    rows = [
        {"harontimel3": 999.0, "timediff": 9999, "time": 9990.0,
         "bataijyu": 57, "datakubun": "7"},   # A: dead_loss
        {"harontimel3": 1.0, "timediff": 0, "time": 90.0,
         "bataijyu": 0, "datakubun": "7"},    # B: scratch_cancel
        {"harontimel3": 1.0, "timediff": 0, "time": 90.0,
         "bataijyu": 57, "datakubun": "9"},   # C: race_cancelled
    ]
    df = pd.DataFrame(rows)
    mod = _get_fukusho_label_module()
    out = mod._canonicalize_markers(df, spec)

    # raw 文字列表現と完全一致
    assert out.loc[0, "is_dead_loss"] == True       # noqa: E712
    assert out.loc[0, "is_scratch_cancel"] == False   # noqa: E712
    assert out.loc[0, "is_race_cancelled"] == False   # noqa: E712

    assert out.loc[1, "is_dead_loss"] == False      # noqa: E712
    assert out.loc[1, "is_scratch_cancel"] == True    # noqa: E712
    assert out.loc[1, "is_race_cancelled"] == False   # noqa: E712

    assert out.loc[2, "is_dead_loss"] == False      # noqa: E712
    assert out.loc[2, "is_scratch_cancel"] == False   # noqa: E712
    assert out.loc[2, "is_race_cancelled"] == True    # noqa: E712


def test_canonicalize_markers_missing_time() -> None:
    """REVIEWS NEW HIGH #3: missing/null time が競走中止と誤判定されるのを防ぐ regression。

    3 variant 全てで harontimel3='999.0' / timediff='9999'（marker_active=True）かつ
    time が missing。pd.isna guard で '__MISSING__' sentinel にマップし time_present=False →
    is_dead_loss=False / is_race_excluded=True に分類する。

    pd.isna guard が無いと str(None)='None' / str(np.nan)='nan' / str(pd.NA)='<NA>' が
    sentinel 集合（'0','0.0','','9999','9999.0'）外となり time_present=True →
    is_dead_loss=True になる silent corruption を検出する regression test。
    """
    spec = _load_label_spec()
    rows = [
        # variant A: time=None (Python None・str(None)='None')
        {"harontimel3": "999.0", "timediff": "9999", "time": None,
         "bataijyu": "057", "datakubun": "7"},
        # variant B: time=np.nan (float NaN・str(np.nan)='nan')
        {"harontimel3": "999.0", "timediff": "9999", "time": np.nan,
         "bataijyu": "057", "datakubun": "7"},
        # variant C: time=pd.NA (pandas NA・str(pd.NA)='<NA>')
        {"harontimel3": "999.0", "timediff": "9999", "time": pd.NA,
         "bataijyu": "057", "datakubun": "7"},
    ]
    df = pd.DataFrame(rows)
    mod = _get_fukusho_label_module()
    out = mod._canonicalize_markers(df, spec)

    for i in range(3):
        assert out.loc[i, "is_dead_loss"] == False, (
            f"variant {i}: missing time は競走中止と判定されてはならない (HIGH #3)"
        )
        assert out.loc[i, "is_race_excluded"] == True, (
            f"variant {i}: marker_active=True AND time_present=False → is_race_excluded=True"
        )
        assert out.loc[i, "is_scratch_cancel"] == False
        assert out.loc[i, "is_race_cancelled"] == False


# ===========================================================================
# Task 2: LABEL-04 edge cases + D-03 §7.2 eligibility + regression tests
# ===========================================================================


def test_dead_heat_all_payout_positive() -> None:
    """同着で PayFukusyoUmaban1..4 に4頭存在（理論値3超過）→ 4頭全て validated=1・dead_heat。"""
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "04",
            "payfukusyoumaban5": "",
        },
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out.loc[out["umaban"].isin(["01", "02", "03", "04"]),
                    "fukusho_hit_validated"] == 1).all()
    assert (out["label_validation_status"] == "dead_heat").all()
    assert (out["is_dead_heat"] == True).all()  # noqa: E712
    assert (out["is_model_eligible"] == True).all()  # noqa: E712


def test_scratch_cancel_excluded() -> None:
    """SE bataijyu='000' の馬行は is_scratch_cancel・validated・予測対象外（race_or_horse_cancelled）。"""
    hr_df, se_df, race_df = _build_label_input_df(8)
    # umaban=5 を取消マーカーに書換
    se_df.loc[se_df["umaban"] == "05", "bataijyu"] = "000"
    se_df.loc[se_df["umaban"] == "05", "harontimel3"] = "999.0"
    se_df.loc[se_df["umaban"] == "05", "timediff"] = "9999"
    se_df.loc[se_df["umaban"] == "05", "time"] = "0"

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    row5 = out[out["umaban"] == "05"].iloc[0]

    assert row5["is_scratch_cancel"] == True  # noqa: E712
    assert row5["label_validation_status"] == "validated"
    assert row5["is_model_eligible"] == False  # noqa: E712
    assert row5["ineligibility_reason"] == "race_or_horse_cancelled"


def test_dead_loss_in_training() -> None:
    """競走中止（time 有り）馬は is_dead_loss=True・fukusho_hit=0・学習に残す（§10.6）。"""
    hr_df, se_df, race_df = _build_label_input_df(8)
    # umaban=7 を競走中止（発走後停止・time 有り）
    se_df.loc[se_df["umaban"] == "07", "bataijyu"] = "054"
    se_df.loc[se_df["umaban"] == "07", "harontimel3"] = "999.0"
    se_df.loc[se_df["umaban"] == "07", "timediff"] = "9999"
    se_df.loc[se_df["umaban"] == "07", "time"] = "9990.0"

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    row7 = out[out["umaban"] == "07"].iloc[0]

    assert row7["is_dead_loss"] == True  # noqa: E712
    assert row7["fukusho_hit_validated"] == 0
    assert row7["fukusho_hit_raw"] == 0
    assert row7["label_validation_status"] == "validated"
    assert row7["is_model_eligible"] == True  # noqa: E712  (§10.6 除外禁止)


def test_dead_loss_in_obstacle_race_excluded_for_obstacle_reason() -> None:
    """REVIEWS HIGH #6: 競走中止+障害の ineligibility_reason は 'obstacle'（dead_loss ではない）。

    compute_is_model_eligible の適用順序で syubetucd 障害が先に評価される。
    純粋 dead_loss 除外（reason='dead_loss' / 'dead_loss_only'）は違反。
    """
    hr_df, se_df, race_df = _build_label_input_df(8, syubetucd="18")  # 18 = 障害
    # umaban=3 を競走中止
    se_df.loc[se_df["umaban"] == "03", "harontimel3"] = "999.0"
    se_df.loc[se_df["umaban"] == "03", "timediff"] = "9999"
    se_df.loc[se_df["umaban"] == "03", "time"] = "9990.0"

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    row3 = out[out["umaban"] == "03"].iloc[0]

    assert row3["is_dead_loss"] == True  # noqa: E712
    assert row3["is_model_eligible"] == False  # noqa: E712
    assert row3["ineligibility_reason"] == "obstacle"  # HIGH #6
    assert row3["ineligibility_reason"] != "dead_loss"
    assert row3["ineligibility_reason"] != "dead_loss_only"


def test_race_cancelled_all_unresolved() -> None:
    """REVIEWS HIGH #4 強化: HR/SE datakubun='9' の全馬行は unresolved / 不適格。

    Plan 03 GREEN の _select_se_state が datakubun IN ('7','9') で SELECT し、
    datakubun='9' の SE 行が落とされずにラベル生成対象になることを前提とする。
    """
    hr_df, se_df, race_df = _build_label_input_df(8, hr_overrides={"datakubun": "9"})
    se_df["datakubun"] = "9"  # 全馬行を race_cancelled に

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert len(out) == 8  # 8頭とも落とされずにラベル生成対象
    assert (out["is_race_cancelled"] == True).all()  # noqa: E712
    assert (out["label_validation_status"] == "unresolved").all()
    assert (out["is_model_eligible"] == False).all()  # noqa: E712
    assert (out["ineligibility_reason"] == "unresolved").all()


def test_select_se_state_includes_datakubun_9() -> None:
    """REVIEWS HIGH #4 regression: _select_se_state のソースが datakubun IN ('7','9') を含む。

    datakubun='7' 単独の WHERE 句は HIGH #4 違反で fail（race_cancelled 376行が消失）。
    """
    mod = _get_fukusho_label_module()
    src = inspect.getsource(mod._select_se_state)
    # '7' と '9' の両方が datakubun に対する IN/= 条件に含まれることを正規表現で検証
    # 許容: datakubun IN ('7','9') / datakubun IN ('7', '9') / datakubun IN ('9','7') 等
    pat = re.compile(r"datakubun\s+IN\s*\([^)]*['\"]7['\"][^)]*['\"]9['\"][^)]*\)", re.IGNORECASE)
    pat_rev = re.compile(r"datakubun\s+IN\s*\([^)]*['\"]9['\"][^)]*['\"]7['\"][^)]*\)", re.IGNORECASE)
    assert pat.search(src) or pat_rev.search(src), (
        "_select_se_state の WHERE 句が datakubun IN ('7','9') を含まない（HIGH #4 違反・"
        "race_cancelled の SE 行が SELECT から落とされる silent data loss）"
    )


def test_fuseiritu_flag2_unresolved() -> None:
    """HR fuseirituflag2='1'（複勝不成立）の全馬行は unresolved・不適格（D-13 分岐保持）。"""
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "fuseirituflag2": "1",
            "payfukusyoumaban1": "00",
            "payfukusyoumaban2": "",
            "payfukusyoumaban3": "",
        },
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["label_validation_status"] == "unresolved").all()
    assert (out["is_model_eligible"] == False).all()  # noqa: E712


def test_tokubaraiflag2_with_payout_validated() -> None:
    """W4 / D-04: 複勝特払 + 対象馬3頭存在 → 対象馬は validated・適格（D-13 分岐保持）。"""
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "tokubaraiflag2": "1",
            "fuseirituflag2": "0",
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    payout_rows = out[out["umaban"].isin(["01", "02", "03"])]
    assert (payout_rows["fukusho_hit_validated"] == 1).all()
    assert (payout_rows["label_validation_status"] == "validated").all()
    assert (payout_rows["is_model_eligible"] == True).all()  # noqa: E712


def test_tokubaraiflag2_without_payout_unresolved() -> None:
    """W4 / D-04 / D-13: 複勝特払のみ（対象馬なし）→ 全馬 unresolved・不適格。"""
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "tokubaraiflag2": "1",
            "fuseirituflag2": "0",
            "payfukusyoumaban1": "00",
            "payfukusyoumaban2": "",
            "payfukusyoumaban3": "",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["label_validation_status"] == "unresolved").all()
    assert (out["is_model_eligible"] == False).all()  # noqa: E712


def test_is_model_eligible_obstacle_syubetucd() -> None:
    """§7.3: syubetucd='18'（障害）は全馬不適格（ineligibility_reason='obstacle'）。"""
    hr_df, se_df, race_df = _build_label_input_df(8, syubetucd="18")
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["is_model_eligible"] == False).all()  # noqa: E712
    assert (out["ineligibility_reason"] == "obstacle").all()


def test_is_model_eligible_newcomer_syubetucd() -> None:
    """§7.3: syubetucd='11'（2歳新馬）は全馬不適格（ineligibility_reason='newcomer'）。"""
    hr_df, se_df, race_df = _build_label_input_df(8, syubetucd="11")
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["is_model_eligible"] == False).all()  # noqa: E712
    assert (out["ineligibility_reason"] == "newcomer").all()


def test_is_model_eligible_maiden_syubetucd_included() -> None:
    """REVIEWS MEDIUM 解決: syubetucd='13'（2歳未勝利・class_level_numeric=0）は §7.2 対象で適格。

    class_level_numeric_minimum=1 と未勝利 class_level_numeric=0 の整合は syubetucd
    maiden list（13/14/15）で解決する。新馬(11,12)は newcomer で除外・未勝利(13,14)/
    条件戦(15)は maiden_syubetucd で適格。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8, syubetucd="13", class_level_numeric=0
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["is_model_eligible"] == True).all()  # noqa: E712
    # ineligibility_reason は None / NaN / null（適格なので理由無し）
    reasons = out["ineligibility_reason"].dropna()
    assert len(reasons) == 0, (
        "syubetucd='13' 未勝利は §7.2 適格・ineligibility_reason は空であるべき"
    )


def test_is_model_eligible_class_below_minimum() -> None:
    """class_level_numeric=0 かつ syubetucd NOT IN maiden_syubetucd は class_below_minimum。

    syubetucd='99'（異常・未勝利でも新馬でもない）+ class_level_numeric=0 → 不適格。
    class_level_numeric=1 + syubetucd='00' の通常ケースは True。
    """
    # 不適格ケース: syubetucd='99' 異常 + class_level_numeric=0
    hr_df, se_df, race_df = _build_label_input_df(
        8, syubetucd="99", class_level_numeric=0
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["is_model_eligible"] == False).all()  # noqa: E712
    assert (out["ineligibility_reason"] == "class_below_minimum").all()

    # 適格ケース: syubetucd='00' + class_level_numeric=1
    hr_df2, se_df2, race_df2 = _build_label_input_df(
        8, syubetucd="00", class_level_numeric=1
    )
    # NOTE: Plan 02-03 (Rule 1 - test typo): 従来 ``compute_fukusho_labels(...)`` と
    # モジュール修飾なしで呼んで NameError になっていたテストバグを ``mod.`` 付きに修正。
    # テストの意図（適格ケースで True を確認）は不変・実装の契約を弱めるものではない。
    out2 = mod.compute_fukusho_labels(hr_df2, se_df2, race_df2, spec=spec)
    assert (out2["is_model_eligible"] == True).all()  # noqa: E712


def test_is_model_eligible_validated_normal() -> None:
    """通常レース（障害/新馬でない・torokutosu>=5・class_level_numeric>=1・正常マーカー）は適格。"""
    hr_df, se_df, race_df = _build_label_input_df(
        8, syubetucd="00", class_level_numeric=2
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    assert (out["is_model_eligible"] == True).all()  # noqa: E712
    reasons = out["ineligibility_reason"].dropna()
    assert len(reasons) == 0


def test_dochakukubun_dead_heat_detection() -> None:
    """同着検出: DochacoTosu='1' でも payout slot4/5 非使用なら dead_heat 判定にならない。

    MEDIUM #2: dead_heat 判定の権威は払戻テーブル slot4/5 使用のみ（DochacoTosu は参考値）。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    # umaban=2,3 を同着（DochacoTosu='1'）に設定・ただし payout slot4/5 は未使用
    se_df.loc[se_df["umaban"] == "02", "dochakutosu"] = "1"
    se_df.loc[se_df["umaban"] == "03", "dochakutosu"] = "1"
    se_df.loc[se_df["umaban"] == "03", "kakuteijyuni"] = "02"  # 同着

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # payout slot4/5 が未使用（payfukusyoumaban4=''）なので dead_heat 判定ではない
    # （payout-table authoritative・DochacoTosu='1' 単独では dead_heat にしない）
    assert (out["label_validation_status"] != "dead_heat").all() or (
        out["is_dead_heat"] == False
    ).all()


def test_select_se_state_no_row_multiplication_on_timediff_merge() -> None:
    """REVIEWS NEW HIGH #2: _select_se_state の timediff merge が 1:1 であることの regression。

    public.n_uma_race 側から timediff を取得する際、両側 datakubun IN ('7','9') でフィルタ +
    merge キーに datakubun を含めて 1:1 merge で row-multiplication を防止する。
    複数 DataKubun 行が存在しても PK+datakubun で厳密 1:1 になる。
    """
    mod = _get_fukusho_label_module()
    src = inspect.getsource(mod._select_se_state)

    # (a) public.n_uma_race からの timediff SELECT が存在
    assert re.search(r"FROM\s+public\.n_uma_race", src, re.IGNORECASE), (
        "_select_se_state が public.n_uma_race からの SELECT を含まない（timediff 取得元欠如）"
    )

    # (b) public.n_uma_race 側の SQL ブロック内で datakubun IN ('7','9') 相当のフィルタが存在
    pat = re.compile(
        r"datakubun\s+IN\s*\([^)]*['\"]7['\"][^)]*['\"]9['\"][^)]*\)", re.IGNORECASE
    )
    pat_rev = re.compile(
        r"datakubun\s+IN\s*\([^)]*['\"]9['\"][^)]*['\"]7['\"][^)]*\)", re.IGNORECASE
    )
    assert pat.search(src) or pat_rev.search(src), (
        "public 側 SELECT の datakubun フィルタが '7' と '9' の両方を含まない（HIGH #2）"
    )

    # (c) merge キーに datakubun を含む（merge / on / left_on / right_on 箇所）
    # merge 呼出し文脈に datakubun が現れることを緩く確認
    assert "datakubun" in src, "merge キーに datakubun が含まれるべき（HIGH #2）"

    # (d) merge 前後の行数一致 assertion / check が存在
    # 許容パターン: assert len(...) / if len(...) != len(...) / RuntimeError 等
    length_check_patterns = [
        r"assert\s+len\(",
        r"len\([^)]*\)\s*==\s*len\(",
        r"len\([^)]*\)\s*!=\s*len\(",
        r"raise\s+RuntimeError",
    ]
    has_length_check = any(
        re.search(p, src) for p in length_check_patterns
    )
    assert has_length_check, (
        "merge 前後の行数一致 assertion が存在しない（HIGH #2 row-multiplication 防止）"
    )


def test_select_se_state_both_selects_share_filter_assertion() -> None:
    """WR-05 regression: _select_se_state が両 SELECT のフィルタ一致を直接 assert する。

    基本 SELECT と timediff SELECT が共に ``datakubun IN ('7', '9')`` を持つことを
    コード内で直接 assert する。片側だけフィルタが退化した場合（例: timediff 側だけ
    ``'9'`` が落ちる）に silent data loss になるのを構造的に防止する。
    """
    mod = _get_fukusho_label_module()
    src = inspect.getsource(mod._select_se_state)

    # WR-05: 両 SELECT の SQL に同一フィルタ文字列が現れることを直接 assert する
    # コードが含まれること。``_required_filter`` 系の assert 文の存在を検証する。
    # 緩い表現（PROJECT_WINDOW_FILTER + datakubun IN ('7', '9') 系の記述）で検出。
    filter_assertion_patterns = [
        # assert ... in sql / assert ... in tsql 形式
        r"assert\s+[^)]*\bin\s+(sql|tsql)\b",
        # 両 SELECT で同一 ``datakubun IN ('7', '9')`` を再利用
        r"['\"]datakubun\s+IN\s*\(\s*['\"]7['\"]\s*,\s*['\"]9['\"]\s*\)",
    ]
    matched = [p for p in filter_assertion_patterns if re.search(p, src, re.IGNORECASE)]
    assert matched, (
        "WR-05: _select_se_state が両 SELECT のフィルタ一致を直接 assert していない。"
        f"マッチしたパターン: {matched}"
    )
