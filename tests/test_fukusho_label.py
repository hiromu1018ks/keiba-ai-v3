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

import datetime as dt
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
                # race_date は normalized.n_race から label ETL 本体が流す列。
                # デフォルトで non-NULL の date を付与しておく（fail-loud 回帰テスト群は
                # 明示的に race_date を drop または空 DataFrame で検証）。
                "race_date": dt.date(2023, 1, 1),
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
    """4-slot HR 扉戻（同着拡張）のレースは dead_heat status に分類される検証。

    WR-04 (iteration 3): 新セマンティクス（payout_places = payout_count）では、8頭レースで
    HR が4 slot 扉戻（slot4='04'）を記録した場合、payout_count=4・payout_places=4 となる。
    SE の KakuteiJyuni 1-4 は全て raw=1（1<=4<=4）で HR 扉戻にも含まれるため validated=1・
    drift 無し。しかし ``is_dead_heat`` は ``payout_count=4 > JRA 理論枠(syussotosu=8 → 3)``
    で True となり、全馬行が 'dead_heat' status に分類される（slot4/5 使用が権威ある同着検出）。
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

    # WR-04 iter3: payout_places = payout_count = 4（HR 扉戻馬番数ベース）
    assert (out["fukusho_payout_places"] == 4).all()
    # is_dead_heat = True（payout_count=4 > JRA 理論枠 3・slot4 使用が権威ある同着検出）
    assert (out["is_dead_heat"] == True).all()  # noqa: E712
    # 全馬行が 'dead_heat' status に分類される
    assert (out["label_validation_status"] == "dead_heat").all()
    # raw/validated は整合（SE 1-4着 は全て HR 扉戻 set に含まれる）・drift 無し
    drift_rows = out[out["fukusho_hit_raw"] != out["fukusho_hit_validated"]]
    assert len(drift_rows) == 0, (
        "WR-04 iter3: HR 4-slot 扉戻と SE 1-4着が整合するケースでは drift は発生しない。"
        f"drift 行: {drift_rows[['umaban','fukusho_hit_raw','fukusho_hit_validated']].to_dict('records')}"
    )


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


def test_payout_places_uses_payout_count_not_syussotosu_or_torokutosu() -> None:
    """WR-04 (iteration 3・最終): 払戻対象頭数は HR PayFukusyoUmaban の払戻馬番数
    （payout_count = 非'00' slot 数）ベース。

    登録8頭（torokutosu=8）・完走4頭（syussotosu=4）で HR 払戻が2頭（payfukusyoumaban3='00'）
    の場合は **2頭払い**。torokutosu/syussotosu いずれの代理値とも一致しないケースで
    payout_count が唯一の正解であることを検証する（実DB R8 相当・発走後中止で完走4頭でも
    HR は2頭払い）。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "torokutosu": "8",
            "syussotosu": "4",  # 発走後中止で完走4頭（HR は2頭払い）
            # HR は2頭払いとして記録（slot3 以降は '00' = 対象外）
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

    # WR-04 iteration 3: HR 払戻馬番数=2 → payout_places=2（torokutosu=8, syussotosu=4
    # いずれとも一致しないが HR 観測事実が唯一の正解）
    assert (out["fukusho_payout_places"] == 2).all(), (
        "WR-04 iter3: torokutosu=8, syussotosu=4, HR payout=['01','02'] は payout_count=2 "
        "→ payout_places=2 でなければならない。torokutosu/syussotosu ベースはいずれも"
        "発走前取消/発走後中止レースで実際の払戻馬番数と一致しない。"
    )


def test_payout_places_scratch_race_3rd_place_excluded() -> None:
    """WR-04 (iteration 3・最終): 発走前取消レース相当で3着馬の raw=0。

    実DBの5件（発走前取消・torokutosu=8/syussotosu=7・HR 払戻 ['06','03','00']）相当。
    HR 払戻は2頭（payout_count=2）なので payout_places=2 となり、SE で3着（kakuteijyuni='03'）
    の馬がいても raw=0・HR 払戻にも含まれないため validated=0・drift 無し。
    torokutosu/syussotosu ベースだと3頭払い計算になり raw=1・HR='00' と食い違う（旧5件
    ドリフトの再現）が、payout_count ベースでは正しく drift 無し。
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
    # SE 側はデフォルト（kakuteijyuni=umaban）のまま。1着=01, 2着=02, 3着=03。
    # HR 扉戻 ['01','02'] と SE 1-2着が整合、3着（umaban='03'）は払戻対象外。

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # payout_places = 2（HR payout_count=2）
    assert (out["fukusho_payout_places"] == 2).all()
    # 3着馬（umaban='03'）は払戻対象外・raw=0・validated=0
    row3 = out[out["umaban"] == "03"].iloc[0]
    assert row3["fukusho_hit_raw"] == 0, (
        "WR-04 iter3: 2頭払いレース（HR payout_count=2）では3着馬は払戻対象外・raw=0。"
        "torokutosu/syussotosu ベース3頭払いだと raw=1 になり HR と食い違う（5件ドリフトの再現）。"
    )
    assert row3["fukusho_hit_validated"] == 0  # HR 払戻 set に含まれない
    # raw と validated が一致（drift 無し）・CR-01 が検知すべきでなかった誤検知の回帰
    drift_rows = out[out["fukusho_hit_raw"] != out["fukusho_hit_validated"]]
    assert len(drift_rows) == 0, (
        "WR-04 iter3: 2頭払い（HR payout_count ベース）正しく計算されたレースでは drift が発生しない。"
        f"drift 行: {drift_rows[['umaban','fukusho_hit_raw','fukusho_hit_validated']].to_dict('records')}"
    )


def test_payout_places_normal_race_8_starters_3_places_regression() -> None:
    """WR-04 regression: HR 扉戻3頭（payout_count=3）の通常レースは3頭払いのまま。

    通常レース（torokutosu=syussotosu=8・HR 扉戻3頭）の payout_places は3であることを検証。
    payout_count ベースに変更しても、HR 払戻馬番数=3 の通常レースは従来通り3（8頭以上の
    JRA 規則通り）である。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        8, hr_overrides={"torokutosu": "8", "syussotosu": "8"}
    )
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # 通常レース・HR 扉戻3頭 → payout_places=3
    assert (out["fukusho_payout_places"] == 3).all()
    # 1-3着馬は raw=1
    assert (out.loc[out["umaban"].isin(["01", "02", "03"]), "fukusho_hit_raw"] == 1).all()
    assert (out.loc[out["umaban"].isin(["04", "05"]), "fukusho_hit_raw"] == 0).all()


def test_payout_places_drift_detection_r4_genuine_horse_number_mismatch() -> None:
    """WR-04 (iteration 3・最終): R4 相当・SE と HR で馬番が入れ違っている genuine drift 検出。

    実DB 2020/05 R4 相当・HR 扉戻 ['03','05','06']・payout_count=3・SE 3着は別馬番。
    torokutosu=syussotosu=10（3頭払い正しい）だが SE 3着 と HR 3着の馬番が入れ違っている
    genuine な矛盾は payout_count ベースでも正しく drift として検出される（payout_places=3
    なので3着の raw=1 だが HR 扉戻に含まれない馬は validated=0・drift）。
    """
    hr_df, se_df, race_df = _build_label_input_df(
        10,  # 10頭立て（torokutosu=syussotosu=10・3頭払い正しい）
        hr_overrides={
            "torokutosu": "10",
            "syussotosu": "10",
            # HR 扉戻: ['03','05','06']（R4 相当・3着馬番=06）
            "payfukusyoumaban1": "03",
            "payfukusyoumaban2": "05",
            "payfukusyoumaban3": "06",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    # SE 側の着順: 1着=03, 2着=05, 3着=08（HR の3着馬番=06 と食い違う・genuine drift）
    se_df.loc[se_df["umaban"] == "03", "kakuteijyuni"] = "01"
    se_df.loc[se_df["umaban"] == "05", "kakuteijyuni"] = "02"
    se_df.loc[se_df["umaban"] == "08", "kakuteijyuni"] = "03"  # SE 3着=08（≠ HR 3着=06）

    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # payout_places = 3（HR payout_count=3・10頭立て）
    assert (out["fukusho_payout_places"] == 3).all()
    # SE 3着（umaban='08'・kakuteijyuni='03'）は raw=1（1<=3<=3）だが HR 扉戻に含まれないため
    # validated=0 → drift。これは genuine な矛盾（R4 相当・CR-01 が検知すべき）。
    row_se_3rd = out[out["umaban"] == "08"].iloc[0]
    assert row_se_3rd["fukusho_hit_raw"] == 1
    assert row_se_3rd["fukusho_hit_validated"] == 0
    drift_rows = out[out["fukusho_hit_raw"] != out["fukusho_hit_validated"]]
    assert len(drift_rows) >= 1, (
        "WR-04 iter3: SE/HR の3着馬番入れ違い（R4 相当）は payout_count ベースでも"
        "drift として検出されなければならない（CR-01 が捕捉すべき genuine drift）。"
    )


def test_payout_places_hr_missing_returns_no_sale() -> None:
    """WR-04 (iteration 3・最終): HR 欠損（unresolved）行は payout_places=0（no_sale）。

    HR merge が left join で HR 行が無い（torokutosu/syussotosu/payout_umaban 全て NaN）
    場合、payout_count も NaN になるため fillna(no_sale) で 0 に正規化される。
    D-13 silent fallback 禁止・安全側・学習除外。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    no_sale = int(spec["payout_places_rules"]["no_sale_marker_value"])

    # HR を空にする（test_unresolved_triggers_hr_missing と同等のシナリオ・payout_count NaN）
    hr_df = pd.DataFrame(columns=[
        "year", "monthday", "jyocd", "kaiji", "nichiji", "racenum", "datakubun",
        "torokutosu", "syussotosu", "fuseirituflag2", "tokubaraiflag2", "henkanflag2",
        "payfukusyoumaban1", "payfukusyoumaban2", "payfukusyoumaban3",
        "payfukusyoumaban4", "payfukusyoumaban5",
    ])
    _, se_df, race_df = _build_label_input_df(8)
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    assert (out["fukusho_payout_places"] == no_sale).all(), (
        f"WR-04 iter3: HR 欠損行の fukusho_payout_places が no_sale({no_sale}) でない: "
        f"{out['fukusho_payout_places'].tolist()}"
    )
    # is_dead_heat も TypeError を起こさず False になること（payout_places=0 で早期 False）
    assert (out["is_dead_heat"] == False).all()  # noqa: E712


def test_payout_count_and_is_dh_handle_pd_na_payout_count() -> None:
    """CR-03 regression: HR merge が left join で HR 欠損行の payout_count が NaN でも
    TypeError を起こさず no_sale に正規化されること。

    WR-04 (iteration 3) で ``fukusho_payout_places`` の計算ベースが payout_count に変更
    されたため、本 regression も HR 欠損シナリオ（payout_count が NaN）を駆動させる。

    ``fillna(no_sale)`` で NaN を no_sale に正規化し ``int()`` 変換の TypeError を回避する。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    no_sale = int(spec["payout_places_rules"]["no_sale_marker_value"])

    # HR 欠損（payout_count が NaN になる）シナリオ: HR を空にする
    hr_df = pd.DataFrame(columns=[
        "year", "monthday", "jyocd", "kaiji", "nichiji", "racenum", "datakubun",
        "torokutosu", "syussotosu", "fuseirituflag2", "tokubaraiflag2", "henkanflag2",
        "payfukusyoumaban1", "payfukusyoumaban2", "payfukusyoumaban3",
        "payfukusyoumaban4", "payfukusyoumaban5",
    ])
    _, se_df, race_df = _build_label_input_df(8)
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # payout_count NaN が fillna(no_sale) で正しく no_sale になること
    assert (out["fukusho_payout_places"] == no_sale).all(), (
        f"CR-03: HR 欠損（payout_count NaN）で fukusho_payout_places が no_sale({no_sale}) "
        f"でない: {out['fukusho_payout_places'].tolist()}"
    )
    # is_dead_heat も TypeError を起こさず False になること
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
                "race_date": dt.date(2023, 1, 1),
            }
        ]
    )
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # HR 欠損行では is_dead_heat が TypeError で crash せず False になる
    assert "is_dead_heat" in out.columns
    assert (out["is_dead_heat"] == False).all()  # noqa: E712


def test_is_dh_false_positive_protect_syussotosu_under_5() -> None:
    """iteration 4 regression: syussotosu < 5（完走4頭以下）のレースで payout_count=2
    が偽の dead_heat にならないこと（2022/07 R8 相当・発走後中止）。

    iteration 3 で ``_is_dh`` を ``payout_count > JRA 理論枠(syussotosu ベース)`` に変更した際、
    ``syussotosu < 5`` では JRA 理論枠=0 になるため ``payout_count(2) > 0`` で常に
    dead_heat 扱いになる false positive があった（実DB で dead_heat 1656→1661・+5馬・
    全て payout_count=2/syussotosu=4）。本テストは R8 相当（完走4頭・2頭払い）が
    dead_heat にならないことを検証する。

    iteration 4 で ``syussotosu < 5`` は dead_heat 判定から除外（保護）するよう修正した。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    # R8 相当: 登録8頭・完走4頭（発走後中止で4頭完走）・HR 払戻2頭
    # HR 扉戻 ['01','02']・payout_count=2・syussotosu=4
    hr_df, se_df, race_df = _build_label_input_df(
        8,
        hr_overrides={
            "torokutosu": "8",
            "syussotosu": "4",  # 完走4頭（発走後中止）
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "00",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # iteration 4: syussotosu=4 < 5 は dead_heat 判定から除外 → is_dead_heat=False
    assert (out["is_dead_heat"] == False).all(), (
        "iteration 4: syussotosu=4（完走4頭以下・発走後中止・R8 相当）で payout_count=2 は"
        "偽の dead_heat になってはならない（JRA 理論枠=0 で payout_count > 0 になる"
        "false positive を防止・syussotosu < 5 は保護）。"
    )
    # dead_heat status にも分類されない
    assert not (out["label_validation_status"] == "dead_heat").any(), (
        "iteration 4: R8 相当レースの label_validation_status が dead_heat になってはならない。"
    )


def test_is_dh_true_slot4_used_syussotosu_8_plus() -> None:
    """iteration 4 regression: syussotosu >= 8 で payout_count=4（slot4 使用）は真の dead_heat。

    8頭以上の通常枠=3・payout_count=4 > 3 で slot4 が使用された真の同着拡張。
    iteration 3 と同様に True を維持する（回帰なし）。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    # 10頭立て・HR 扉戻 ['01','02','03','04']（slot4 使用・payout_count=4）
    hr_df, se_df, race_df = _build_label_input_df(
        10,
        hr_overrides={
            "torokutosu": "10",
            "syussotosu": "10",
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "04",
            "payfukusyoumaban5": "",
        },
    )
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # syussotosu=10 >= 8 → 標準3・payout_count=4 > 3 → True（slot4 使用 = 真の dead_heat）
    assert (out["is_dead_heat"] == True).all()  # noqa: E712
    assert (out["label_validation_status"] == "dead_heat").all()


def test_is_dh_true_payout_count_3_syussotosu_6() -> None:
    """iteration 4 regression: syussotosu=6（5-7頭）で payout_count=3 は真の dead_heat。

    5-7頭の標準枠=2・payout_count=3 > 2 で slot3 の同着拡張（3着同着）。
    iteration 3 と同様に True を維持する（回帰なし）。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    # 6頭立て・HR 扉戻 ['01','02','03']（3着同着・payout_count=3 > 標準2）
    hr_df, se_df, race_df = _build_label_input_df(
        6,
        hr_overrides={
            "torokutosu": "6",
            "syussotosu": "6",
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # syussotosu=6（5-7頭）→ 標準2・payout_count=3 > 2 → True（3着同着拡張）
    assert (out["is_dead_heat"] == True).all()  # noqa: E712
    assert (out["label_validation_status"] == "dead_heat").all()


def test_is_dh_false_payout_count_3_syussotosu_10() -> None:
    """iteration 4 regression: syussotosu=10（8頭以上）・payout_count=3（標準枠=3）は
    dead_heat ではない。

    8頭以上の標準枠=3・payout_count=3 は標準枠内（> ではない）なので dead_heat=False。
    通常の3頭払いレースは dead_heat にならない（iteration 3 と同様）。
    """
    spec = _load_label_spec()
    mod = _get_fukusho_label_module()
    # 10頭立て・HR 扉戻 ['01','02','03']（標準3頭払い・payout_count=3 = 標準3）
    hr_df, se_df, race_df = _build_label_input_df(
        10,
        hr_overrides={
            "torokutosu": "10",
            "syussotosu": "10",
            "payfukusyoumaban1": "01",
            "payfukusyoumaban2": "02",
            "payfukusyoumaban3": "03",
            "payfukusyoumaban4": "",
            "payfukusyoumaban5": "",
        },
    )
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)
    # syussotosu=10 >= 8 → 標準3・payout_count=3 ≯ 3 → False（通常の3頭払い）
    assert (out["is_dead_heat"] == False).all()  # noqa: E712
    assert not (out["label_validation_status"] == "dead_heat").any()


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
    # CR-04 (iteration 6): race_cancelled レースは複勝発売不成立・is_fukusho_sale_available=False
    # torokutosu ベース（登録>=5 → True）でも当日中止なら False に正規化される。
    assert (out["is_fukusho_sale_available"] == False).all()  # noqa: E712


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


def test_select_se_state_uses_inner_merge_with_timediff_nan_guard() -> None:
    """WR-10 regression: _select_se_state の timediff merge が how="inner" で
    両側一致を強制し、merge 後 timediff NaN guard で silent leak を防止する。

    how="left" では:
      (a) timediff_df 側の余剰行が silent に捨てられ検知不能
      (b) timediff_df 側の欠損行で timediff が NaN になり silent に進む
          → 競走中止馬が正常馬に誤分類される silent leak 源（D-13）

    inner merge + timediff NaN guard で構造的に防止する。本テストは実行時挙動
    （DB 必須）ではなくコード契約の regression として検証する。
    """
    mod = _get_fukusho_label_module()
    src = inspect.getsource(mod._select_se_state)

    # (a) how="inner" を使用（how="left" を明示的に禁止）
    # merge(..., how="inner") のパターンを検出・how="left" が残っていないことを確認
    assert re.search(r'\.merge\([^)]*how\s*=\s*["\']inner["\']', src), (
        'WR-10: _select_se_state の timediff merge が how="inner" を使用していない（silent leak 源）'
    )
    assert not re.search(r'\.merge\([^)]*how\s*=\s*["\']left["\']', src), (
        'WR-10: _select_se_state に how="left" merge が残存している（WR-10 違反）'
    )

    # (b) merge 後の行数不一致検知（inner merge でも se 側と merged 側で行数が
    # 異なる場合 = 余剰行 or 欠損行 がある場合に RuntimeError で fail-fast）
    assert re.search(r'len\(merged\)\s*!=\s*pre_len', src) or re.search(
        r'len\(merged\)\s*!=\s*len\(se_df\)', src
    ), "WR-10: merge 後の行数不一致検知 (RuntimeError) が存在しない"

    # (c) merge 後 timediff NaN guard（inner merge 後でも timediff が全行非 NaN
    # であることを assert・NaN があれば RuntimeError で fail-fast）
    assert re.search(r'timediff["\']?\]\.isna\(\)\.any\(\)', src) or re.search(
        r'timediff["\']?\]\.isna\(\)\.sum\(\)', src
    ), "WR-10: merge 後 timediff NaN guard (RuntimeError) が存在しない"


# ===========================================================================
# regression: race_date 流入（Phase 2 負債 / Phase 5 backtest 前提）
# ---------------------------------------------------------------------------
# label.fukusho_label.race_date は label ETL 本体が normalized.n_race から流す。
# _RACE_META_SELECT_COLUMNS から race_date が欠落すると全行 NULL になり、backtest の
# _filter_label_by_period が test 窓で0件 → fail（Phase 5 実データ backtest 障害）。
# backfill（src/etl/label_race_date_backfill.py）は「既に NULL になった過去負債の回復」
# 専用であり、本丸は label ETL 本体が race_date を流すこと。両者の回帰を構造的に保証する。
# ===========================================================================


def test_race_meta_select_columns_includes_race_date() -> None:
    """regression: _select_race_meta が normalized.n_race から race_date を SELECT する。

    race_date は label.fukusho_label.race_date の正しいソース（normalized.n_race.race_date
    = raw の year+monthday から normalized ETL が構築）。_RACE_META_SELECT_COLUMNS から
    race_date が欠落すると _select_race_meta の race_df に race_date が含まれなくなり、
    compute_fukusho_labels の出力 race_date が全行 NULL になる（Phase 2 負債の発生元）。
    """
    mod = _get_fukusho_label_module()
    assert "race_date" in mod._RACE_META_SELECT_COLUMNS, (
        "_RACE_META_SELECT_COLUMNS に race_date が無い（label ETL 本体が race_date を "
        "流さない → label.fukusho_label.race_date 全行 NULL 再発・Phase 2 負債回帰）"
    )


def test_compute_fukusho_labels_propagates_race_date() -> None:
    """regression: compute_fukusho_labels が race_df の race_date を出力へ伝播する。

    race_df（normalized.n_race 由来）に race_date が含まれる場合、1行/馬の出力にも
    race_date が non-NULL で伝播することを検証。伝播しないと backtest の
    _filter_label_by_period が test 窓で0件になり fail（Phase 5 実データ backtest 障害）。
    """
    import datetime as dt  # noqa: PLC0415

    mod = _get_fukusho_label_module()
    spec = _load_label_spec()
    hr_df, se_df, race_df = _build_label_input_df(8)
    # race_df に race_date を付与（normalized.n_race 相当・1レース全馬で同一値）
    race_df = race_df.copy()
    expected_date = dt.date(2023, 1, 1)
    race_df["race_date"] = expected_date

    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # race_date 列が存在し、全行 non-NULL で race_df の値と一致（1レース8馬）
    assert "race_date" in out.columns, "出力に race_date 列が無い（伝播漏れ）"
    assert len(out) == 8
    assert out["race_date"].notna().all(), (
        f"race_date に NULL が {int(out['race_date'].isna().sum())} 件ある（伝播漏れ）"
    )
    unique_dates = pd.Series(out["race_date"].unique()).dropna()
    assert len(unique_dates) == 1, "race_date が複数値（1レース内で不整合）"
    assert pd.Timestamp(unique_dates.iloc[0]) == pd.Timestamp(expected_date), (
        "race_date が race_df の値と一致しない（伝播不正）"
    )


# ---------------------------------------------------------------------------
# regression: race_date fail-loud（Phase 2 負債 / silent corruption 再発防止）
# ---------------------------------------------------------------------------
# 2026-06-23/06-24 に label.fukusho_label.race_date 全行 NULL が2回再発。従来の
# `if "race_date" not in merged.columns: merged["race_date"] = pd.NA` fallback が
# race_date 伝播失敗を黙って全行 NULL 化する構造的欠陥だった。再発時に止まり、
# なぜ race_date が抜けたか（race_df 空 / race_date 列なし / キー不整合）が
# ログから分かる仕組みにする（fail-loud + 診断ログ）。根本原因は再発時の診断
# ログで特定する。以下3テストは race_date 伝播失敗ケースで RuntimeError を
# raise することを検証する。
# ===========================================================================


def test_compute_fukusho_labels_raises_on_empty_race_df() -> None:
    """regression: race_df が空（0行）の場合・compute_fukusho_labels が RuntimeError を raise。

    race_df が空の場合、race_date 列が merged に伝播しない（compute_fukusho_labels の
    race_df merge が0行の race_df と left join しても race_date 列自体が生えない）。
    従来は黙って pd.NA fallback で全行 NULL 化していたが、fail-loud で RuntimeError を
    raise して再発時に原因（race_df 空）を特定可能にする。
    """
    mod = _get_fukusho_label_module()
    spec = _load_label_spec()
    hr_df, se_df, _ = _build_label_input_df(8)
    # race_df を空 DataFrame（race_date 列なし・行0）に置換
    race_df = pd.DataFrame(columns=["year", "monthday", "jyocd", "kaiji", "nichiji", "racenum"])

    with pytest.raises(RuntimeError, match="race_date"):
        mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)


def test_compute_fukusho_labels_raises_on_missing_race_date_column() -> None:
    """regression: race_df に race_date 列が無い場合・RuntimeError を raise する。

    race_df は1行あるが race_date 列を持たない場合（デフォルトの _build_label_input_df
    は race_date 列を含まない）、compute_fukusho_labels は race_date を伝播できず
    RuntimeError を raise する。既存 test_compute_fukusho_labels_propagates_race_date は
    race_df に race_date を付与してから呼ぶため GREEN を維持。
    """
    mod = _get_fukusho_label_module()
    spec = _load_label_spec()
    # _build_label_input_df のデフォルト race_df は race_date 列を含むため明示的に drop
    hr_df, se_df, race_df = _build_label_input_df(8)
    race_df = race_df.drop(columns=["race_date"])

    with pytest.raises(RuntimeError, match="race_date"):
        mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)


def test_compute_fukusho_labels_normal_case_no_diagnostic_log() -> None:
    """regression: 正常ケース（race_date 全行 non-NULL）は RuntimeError 未発生・挙動不变。

    race_df に race_date が存在し全行 non-NULL で伝播する通常ケースでは、
    RuntimeError が raise されず・logger.error も出力されず・出力の race_date が
    全行 non-NULL であることを検証（正常ケース挙動不变保証）。
    """
    import datetime as dt  # noqa: PLC0415

    mod = _get_fukusho_label_module()
    spec = _load_label_spec()
    hr_df, se_df, race_df = _build_label_input_df(8)
    race_df = race_df.copy()
    expected_date = dt.date(2023, 1, 1)
    race_df["race_date"] = expected_date

    # 正常ケース: RuntimeError 未発生
    out = mod.compute_fukusho_labels(hr_df, se_df, race_df, spec=spec)

    # 出力の race_date が全行 non-NULL（正常伝播）
    assert "race_date" in out.columns, "出力に race_date 列が無い（伝播漏れ）"
    assert out["race_date"].notna().all(), (
        f"正常ケースで race_date に NULL が {int(out['race_date'].isna().sum())} 件ある"
    )
    unique_dates = pd.Series(out["race_date"].unique()).dropna()
    assert len(unique_dates) == 1
    assert pd.Timestamp(unique_dates.iloc[0]) == pd.Timestamp(expected_date)
