# ruff: noqa: E501, F401  (長い docstring / SQL リテラル・Plan 05-05 で今後使用予定 import を保持)
"""Phase 5 entry point: BT窓再学習 + フル行列 backtest + reports/05-backtest 生成.

D-03 (BT窓再学習ループ) / BACK-01..04 / §11.2 odds policy 固定 / §15.5 BT窓 /
D-04 (BL-3 確定オッズ popular baseline) / SC#4 (bit-identical) / §19.1 再現性聖域 を
実装する Phase 5 の最終成果物エントリポイント。

起動フロー (run_train_predict.py パターン・masked DSN・try/finally):

  1. ``Settings`` から ``dsn_masked`` / ``etl_dsn_masked`` をログ出力 (生 DSN 絶対禁止・T-05-17)
  2. readonly pool + etl pool 構築 (``--synthetic`` の場合は構築しない)
  3. BT窓再学習ループ (``BT_WINDOWS`` × model_type):
     a. ``_carve_calib_from_train_tail(bt)`` で train_start 固定・train_end=calib_start-1day (HIGH-B cycle-2)
     b. BT窓 train 行のみで ``fit_category_map`` → orchestrator に ``category_map`` で伝播 (HIGH-5)
     c. ``train_and_predict(..., split_periods=periods, category_map=bt_map, as_of_datetime=FIXED_REPRODUCE_TS)``
  4. フル行列 backtest (5窓 × 2 policy × 2 model + 5 BL-3 = 25):
     a. ``fetch_jodds`` (or 合成 mock) → ``select_odds_snapshot`` で per-horse 固定時点 odds
     b. HIGH-2: ``pred_df.merge(snapshot, on=['race_key','umaban'])`` + 行数不変 assert
     c. ``compute_ev_and_rank`` → ``select_bets`` → full_candidate table (MEDIUM-A)
     d. HIGH-C: HARAI race-level merge (``validate='many_to_one'``) + label 馬単位 merge
     e. ``determine_stake_payout`` で会計 → MEDIUM cycle-3: non-selected 会計ゼロ化
     f. ``compute_backtest_metrics`` (selected_flag=True filter) → ``load_backtest`` (full_candidate)
  5. MEDIUM-B horse-level usable-odds coverage gate (``--synthetic`` 外す実行時)
  6. ``generate_report`` で reports/05-backtest.{md,json} (BACK-04 winner 報告禁止)

Usage::

    # 合成データ E2E smoke (実JODDS/DB 不要)
    uv run python scripts/run_backtest.py --synthetic --bt-filter BT-1

    # 実データ (JODDS 取得完了後・後続 Plan 05-06 checkpoint)
    uv run python scripts/run_backtest.py --snapshot-id 20260620-1a-postreview-v2

    # SC#4 bit-identical 検証
    uv run python scripts/run_backtest.py --synthetic --bt-filter BT-1 --check-reproduce
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from psycopg.errors import Error as PsycopgError  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.db.connection import make_pool, readonly_cursor, write_cursor  # noqa: E402
from src.ev.bl3_betting import (  # noqa: E402
    BL3_BETTING_CAVEAT,
    BL3_MODEL_TYPE,
    BL3_ODDS_SNAPSHOT_POLICY,
    select_bl3_bets,
)
from src.ev.ev_rank import compute_ev_and_rank  # noqa: E402
from src.ev.metrics import compute_backtest_metrics  # noqa: E402
from src.ev.odds_snapshot import (  # noqa: E402
    ODDS_SNAPSHOT_POLICIES,
    ODDS_SOURCE_TYPE_JODDS,
    fetch_jodds,
    select_odds_snapshot,
)
from src.ev.purchase_simulator import (  # noqa: E402
    FUKUSHO_EV_V1_STRATEGY,
    select_bets,
)
from src.ev.refund_accounting import determine_stake_payout  # noqa: E402
from src.ev.report import REPORT_COLUMNS, generate_report  # noqa: E402
from src.model.baseline import fetch_market_data  # noqa: E402
from src.model.data import (  # noqa: E402
    SNAPSHOT_PATH,
    build_training_frame,
    load_feature_matrix,
    load_labels,
)
from src.model.orchestrator import (  # noqa: E402
    FIXED_REPRODUCE_TS,
    _assert_deterministic,
    train_and_predict,
)
from src.utils.category_map import fit_category_map  # noqa: E402
from src.utils.group_split import BT_WINDOWS, BTWindow  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_backtest")

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 全 backtest 行列 (5窓 × 2 policy × 2 model + 5 BL-3 = 25)
ALL_MODEL_TYPES: tuple[str, ...] = ("lightgbm", "catboost")
ALL_POLICIES: tuple[str, ...] = ("30min_before", "10min_before")

# MEDIUM-B cycle-2: horse-level usable-odds coverage 閾値 (既定 0.90)
JODDS_HORSE_COVERAGE_THRESHOLD: float = 0.90
# secondary race-level coverage 閾値 (元 MEDIUM-05)
JODDS_RACE_COVERAGE_THRESHOLD: float = 0.95

# BT窓 calib carve のデフォルトサイズ (calib を BT窓 train 尾から切る・HIGH-B cycle-2)
# 例: BT-1 (train_end=2022-12-31) → calib_start=2022-07-01 / calib_end=2022-12-31
_DEFAULT_CALIB_MONTHS = 6


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する。"""
    parser = argparse.ArgumentParser(
        description=(
            "Phase 5 entry point: BT-window retraining + full-matrix backtest + "
            "reports/05-backtest (BACK-01..04 / D-03 / D-04 / §15.5 / §19.1)"
        ),
    )
    parser.add_argument(
        "--snapshot-id",
        default="20260620-1a-postreview-v2",
        help="feature snapshot identifier (D-01, default: 20260620-1a-postreview-v2)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help=(
            "合成データ E2E smoke (実JODDS/DB 未完でも検証可能)。"
            "mock JODDS/label/HARAI/prediction でフル行列を完走し reports/05-backtest を生成。"
        ),
    )
    parser.add_argument(
        "--bt-filter",
        default=None,
        help="BT窓名絞り (例: BT-1・カンマ区切りで複数指定可)。既定は全5窓。",
    )
    parser.add_argument(
        "--check-reproduce",
        action="store_true",
        help="SC#4 bit-identical 検証 (seed=42 + FIXED_REPRODUCE_TS・BT窓指定推奨)",
    )
    parser.add_argument(
        "--version-n",
        type=int,
        default=1,
        help="model_version 採番の version 番号 (D-10, default: 1)",
    )
    parser.add_argument(
        "--no-write-db",
        action="store_true",
        help="backtest.fukusho_backtest への書込を skip (dry run)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="report 出力ディレクトリ (default: reports)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# _carve_calib_from_train_tail — HIGH-B cycle-2 calib carve
# ---------------------------------------------------------------------------
def _carve_calib_from_train_tail(
    bt: BTWindow,
    *,
    calib_months: int = _DEFAULT_CALIB_MONTHS,
) -> dict[str, tuple[str, str]]:
    """BT窓 train 尾から calib を切り出し・split_3way 用の periods dict を返す (HIGH-B cycle-2)。

    **HIGH-B cycle-2 修正**: ``train_start`` は固定し・``train_end = calib_start - 1day`` に短縮する
    (train の *開始* でなく *終了* を前に詰めて calib 分の空きを作る)。これにより train と calib の
    時系列順序 (``max(train) < min(calib) < max(calib) < min(test)``) が全 BT窓で deterministic に保証される。

    例 BT-1 (train_start='2019-06-01', train_end='2022-12-31'):
        train = ('2019-06-01', '2022-06-30')  # train_end を手前に詰める
        calib = ('2022-07-01', '2022-12-31')  # BT窓 train 尾の6ヶ月
        test  = bt.test_start..bt.test_end

    Parameters
    ----------
    bt : BTWindow
    calib_months : int
        calib 区間の長さ (月単位・既定6)。BT窓 train_end から遡って calib_start を決める。

    Returns
    -------
    dict
        ``{"train": (start, end), "calib": (start, end), "test": (start, end)}``。
        ``split_3way`` に ``periods=`` で渡す。
    """
    import pandas as pd

    bt_train_end = pd.Timestamp(bt.train_end)
    # calib_end は BT窓 train_end に一致
    calib_end = bt_train_end
    # calib_start = calib_end から calib_months 月遡る (月初に正規化)
    calib_start = (calib_end.replace(day=1) - pd.DateOffset(months=calib_months - 1)).normalize()
    # train_end = calib_start - 1day (HIGH-B cycle-2: train_start 固定・train_end を手前に詰める)
    train_end_carved = calib_start - pd.Timedelta(days=1)

    return {
        "train": (bt.train_start, train_end_carved.strftime("%Y-%m-%d")),
        "calib": (calib_start.strftime("%Y-%m-%d"), calib_end.strftime("%Y-%m-%d")),
        "test": (bt.test_start, bt.test_end),
    }


# ---------------------------------------------------------------------------
# BT窓選択 / category map fit
# ---------------------------------------------------------------------------
def _select_bt_windows(bt_filter: str | None) -> list[BTWindow]:
    """``--bt-filter`` で指定された BT窓名のリストを返す (None は全5窓)。"""
    if bt_filter is None:
        return list(BT_WINDOWS)
    wanted = {w.strip() for w in bt_filter.split(",") if w.strip()}
    selected = [bt for bt in BT_WINDOWS if bt.name in wanted]
    if not selected:
        raise ValueError(
            f"--bt-filter {bt_filter!r} に一致する BT窓が無い (available={[b.name for b in BT_WINDOWS]})"
        )
    return selected


# HIGH-5: BT窓 train 期間のみで fit_category_map を呼び・生 ID 列ごとに frozen map を構築する。
# orchestrator._apply_category_map が ``_code`` 列をこの map で再構築し・test 窓未観測 ID は
# ``__UNSEEN__`` sentinel になる (§14.3 leak-safe categorical handling)。
def _fit_bt_category_map(
    feature_df: pd.DataFrame,  # type: ignore[name-defined]
    train_start: str,
    train_end: str,
) -> dict[str, Any] | None:
    """BT窓 train 期間のみの feature_df 行から ``fit_category_map`` で frozen map を構築する (HIGH-5)。

    feature_df が ``jockey_id`` 等の生 ID 列を含む場合のみ map を構築。生 ID 列を含まない
    (例: 合成 mock・既に _code のみの snapshot) 場合は ``None`` を返す (Phase 4 等価・A5)。
    """
    import pandas as pd

    # train 期間の行のみ抽出
    if "race_date" not in feature_df.columns:
        return None
    train_mask = feature_df["race_date"].between(train_start, train_end)
    train_df = feature_df.loc[train_mask]

    raw_id_cols = ["jockey_id", "trainer_id", "sire_id", "bms_id", "horse_id"]
    bt_map: dict[str, Any] = {}
    for col in raw_id_cols:
        if col not in train_df.columns:
            continue
        series = train_df[col]
        # NaN は fit_category_map 側で __MISSING__ 扱い
        if series.notna().sum() == 0:
            continue
        bt_map[col] = fit_category_map(series)

    return bt_map if bt_map else None


# ---------------------------------------------------------------------------
# synthetic data builders (test 用・--synthetic 時に使用)
# ---------------------------------------------------------------------------
def _build_synthetic_feature_df() -> pd.DataFrame:  # type: ignore[name-defined]
    """``--synthetic`` 用の最小 feature_df mock を構築する。

    BT-1 (train 2019-06..2022 / calib 2022-07..12 / test 2023) が空にならないよう十分な行数を
    確保する。FEATURE_COLUMNS 互換ではなく・run_backtest --synthetic は train_and_predict を
    呼ばず (モデル学習は skip) ・pred_df / odds / label を直接合成するため FEATURE 内容は問わない。

    **select_odds_snapshot の pandas merge_asof 制約**: ``merge_asof`` は ``left_on`` 列
    (cutoff_datetime) の大域的単調増加を要求する。race_key と race_start_datetime の sort 順序が
    一致するよう race_key 文字列を ``{year}-{month:02d}-{jyocd}-...`` 形式で構築する
    (race_key 辞書順 = race_start_datetime 時系列順)。
    """
    import pandas as pd

    # BT-1..5 全窓の train/calib/test 期間をカバーする合成 race_date を生成
    rows = []
    race_key_idx = 0
    # 2019-01..2025-12 の各月・各 jyocd に2レース × 8頭を生成
    for year in range(2019, 2026):
        for month in range(1, 13):
            for jyocd in ("05", "06"):  # 2競馬場
                for racenum in (1, 2):  # 2レース/月/競馬場
                    race_key_idx += 1
                    race_date = pd.Timestamp(year=year, month=month, day=5)
                    # select_odds_snapshot の merge_asof が left_on/right_on の大域単調増加を
                    # 要求するため・race_start_datetime を race_key sort 順 (= 時系列順) で
                    # 単調増加させる。jyocd/racenum を時刻に反映し・同一 race_key 内では
                    # 全馬同一時刻・race_key 跨ぎで必ず時刻が進むようにする。
                    hour = 10 + int(jyocd) - 5  # jyocd=05→10時・06→11時
                    minute = (racenum - 1) * 30  # racenum=1→00分・2→30分
                    race_start_dt = race_date + pd.Timedelta(hours=hour, minutes=minute)
                    # race_key を year-month-jyocd-kaiji-nichiji-racenum 順にして
                    # race_key sort = race_start_datetime sort と一致させる (merge_asof 制約)
                    race_key = f"{year}-{month:02d}-{jyocd}-1-{month:02d}-{racenum}"
                    for umaban in range(1, 9):  # 8頭
                        rows.append({
                            "year": str(year),
                            "jyocd": jyocd,
                            "kaiji": "1",
                            "nichiji": f"{month:02d}",
                            "racenum": str(racenum),
                            "umaban": umaban,
                            "kettonum": 1000000 + race_key_idx * 10 + umaban,
                            "race_key": race_key,
                            "race_date": race_date,
                            "race_start_datetime": race_start_dt,
                            "jockey_id": f"jk{race_key_idx % 50}",
                            "trainer_id": f"tr{race_key_idx % 30}",
                            "sire_id": f"sr{race_key_idx % 40}",
                            "bms_id": f"bm{race_key_idx % 35}",
                            "horse_id": f"hs{race_key_idx * 10 + umaban}",
                            "p_fukusho_hit": 0.30 - 0.03 * (umaban - 1),
                            "fukusho_hit_validated": 1 if umaban <= 3 else 0,
                            "is_model_eligible": True,
                            "label_validation_status": "validated",
                            "is_fukusho_sale_available": True,
                            "fukusho_payout_places": 3,
                            "is_scratch_cancel": False,
                            "is_race_excluded": False,
                            "is_race_cancelled": False,
                            "is_dead_loss": False,
                        })
    return pd.DataFrame(rows)


def _build_synthetic_jodds_df(feature_df_test: pd.DataFrame) -> pd.DataFrame:  # type: ignore[name-defined]
    """``--synthetic`` 用の JODDS snapshot mock を構築する (馬単位)。

    test 期間の各 (race_key, umaban) に対し・race_start_datetime - 20分の snapshot 1件を生成する。

    **select_odds_snapshot の merge_asof 制約**: pandas merge_asof は left_on/right_on の
    大域的単調増加を要求する (by= セマンティクスに関わらず)。合成データは各馬1件の snapshot で・
    race_key sort 順 = race_start_datetime sort 順 = happyo_datetime sort 順 になるよう構築する。
    """
    import pandas as pd

    rows = []
    for _, r in feature_df_test.iterrows():
        race_start = r["race_start_datetime"]
        # snapshot 時刻 = race_start - 20分 (cutoff 30分/10分のいずれでも選択される安全な時刻)
        snap_time = race_start - pd.Timedelta(minutes=20)
        mmdd = f"{snap_time.month:02d}{snap_time.day:02d}"
        hhmm = f"{snap_time.hour:02d}{snap_time.minute:02d}"
        rows.append({
            "year": r["year"],
            "monthday": mmdd,
            "jyocd": r["jyocd"],
            "kaiji": r["kaiji"],
            "nichiji": r["nichiji"],
            "racenum": r["racenum"],
            "umaban": int(r["umaban"]),
            "happyotime": f"{mmdd}{hhmm}",
            "fukuoddslow": "0012",
            "fukuoddshigh": "0018",
            "fukusyoflag": "7",
            "datakubun": "1",
            "race_key": r["race_key"],
            "happyo_datetime": snap_time,
        })
    return pd.DataFrame(rows)


def _build_synthetic_label_df(feature_df_test: pd.DataFrame) -> pd.DataFrame:  # type: ignore[name-defined]
    """``--synthetic`` 用の label DataFrame (馬単位) を構築する。"""
    label_cols = [
        "race_key", "umaban",
        "is_scratch_cancel", "is_race_cancelled", "is_race_excluded",
        "is_dead_loss", "is_fukusho_sale_available",
        "fukusho_payout_places", "fukusho_hit_validated",
    ]
    return feature_df_test[label_cols].copy()


def _build_synthetic_harai_df(feature_df_test: pd.DataFrame) -> pd.DataFrame:  # type: ignore[name-defined]
    """``--synthetic`` 用の HARAI race-level 払戻 DataFrame を構築する。

    HARAI は race-level slot レコード (umaban 列なし・1レース1行・HIGH-C cycle-2)。
    """
    races = feature_df_test.drop_duplicates("race_key")[["race_key"]].copy()
    # slot1=umaban1 (150円) / slot2=umaban2 (200円) / slot3=umaban3 (250円)
    races["fuseirituflag2"] = "0"
    races["henkanflag2"] = "0"
    races["tokubaraiflag2"] = "0"
    races["payfukusyoumaban1"] = "01"
    races["payfukusyopay1"] = "0000150"
    races["payfukusyoumaban2"] = "02"
    races["payfukusyopay2"] = "0000200"
    races["payfukusyoumaban3"] = "03"
    races["payfukusyopay3"] = "0000250"
    races["payfukusyoumaban4"] = "00"
    races["payfukusyopay4"] = "0000000"
    races["payfukusyoumaban5"] = "00"
    races["payfukusyopay5"] = "0000000"
    return races


def _build_synthetic_pred_df(feature_df_test: pd.DataFrame) -> pd.DataFrame:  # type: ignore[name-defined]
    """``--synthetic`` 用の予測 DataFrame を構築する (train_and_predict を呼ばない)。

    ``race_start_datetime`` を必ず含める (HIGH-1: ``select_odds_snapshot`` が race_start_datetime
    基準で cutoff を計算するため・馬単位 race_times に必須)。また ``select_bets`` / label merge /
    refund_accounting が消費する ``is_fukusho_sale_available`` / ``is_model_eligible`` /
    ``is_scratch_cancel`` / ``is_race_excluded`` / ``is_race_cancelled`` / ``is_dead_loss`` /
    ``fukusho_payout_places`` / ``fukusho_hit_validated`` 列も保持する (合成データは feature_df
    から直接予測として扱うため・select_bets の事前 filter が動作するのに必要)。
    """
    base_cols = [
        "year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum",
        "race_key", "race_date", "race_start_datetime", "p_fukusho_hit",
        "is_fukusho_sale_available", "is_model_eligible",
        "is_scratch_cancel", "is_race_excluded", "is_race_cancelled", "is_dead_loss",
        "fukusho_payout_places", "fukusho_hit_validated",
    ]
    cols = [c for c in base_cols if c in feature_df_test.columns]
    return feature_df_test[cols].copy()


# ---------------------------------------------------------------------------
# pipeline helpers
# ---------------------------------------------------------------------------
def _build_race_times_per_horse(pred_df: pd.DataFrame) -> pd.DataFrame:  # type: ignore[name-defined]
    """予測馬単位の ``race_times`` (race_key + umaban + race_start_datetime) を構築する (HIGH-1)。

    ``select_odds_snapshot`` は ``by=['race_key','umaban']`` で per-horse snapshot を返すため・
    ``race_times`` も馬単位であることが前提 (Plan 03 契約)。
    """
    if "race_start_datetime" not in pred_df.columns:
        raise RuntimeError(
            "_build_race_times_per_horse: pred_df に race_start_datetime 列がない (HIGH-1 前提違反)"
        )
    return pred_df[["race_key", "umaban", "race_start_datetime"]].copy()


def _attach_provenance(
    df: pd.DataFrame,  # type: ignore[name-defined]
    *,
    backtest_id: str,
    bt_name: str,
    odds_policy: str,
    model_type: str,
    model_version: str,
    feature_snapshot_id: str,
    periods: dict[str, tuple[str, str]],
) -> pd.DataFrame:  # type: ignore[name-defined]
    """full_candidate_with_accounting に ``BACKTEST_COLUMNS`` の provenance 列を付与する。"""
    out = df.copy()
    out["backtest_id"] = backtest_id
    out["backtest_strategy_version"] = FUKUSHO_EV_V1_STRATEGY
    out["odds_snapshot_policy"] = odds_policy
    out["train_period_start"] = periods["train"][0]
    out["train_period_end"] = periods["train"][1]
    out["test_period_start"] = periods["test"][0]
    out["test_period_end"] = periods["test"][1]
    out["model_type"] = model_type
    out["model_version"] = model_version
    out["feature_snapshot_id"] = feature_snapshot_id
    return out


def _attach_accounting(
    df_with_label: pd.DataFrame,  # type: ignore[name-defined]
) -> pd.DataFrame:  # type: ignore[name-defined]
    """``determine_stake_payout`` を各行に適用し・stake/refund/payout/profit/effective_stake を付与する。

    元の ``df_with_label`` が ``stake`` 等の会計列を持つ場合は事前に削除してから付与する
    (select_bets / select_bl3_bets が ``stake`` 列を設定するため・determine_stake_payout の
    戻り値と concat すると同名列が複数でき pandas が Series を返す問題を防止)。
    """
    import pandas as pd

    # 既存の会計列を削除 (select_bets / select_bl3_bets 由来の stake 等)
    accounting_cols = ["stake", "refund", "payout", "profit", "effective_stake"]
    base = df_with_label.drop(
        columns=[c for c in accounting_cols if c in df_with_label.columns],
        errors="ignore",
    )
    accounting = base.apply(determine_stake_payout, axis=1, result_type="expand")
    accounting.columns = accounting_cols
    out = pd.concat([base, accounting], axis=1)
    # BACKTEST_COLUMNS 互換の補助会計列を付与
    out["refund_flag"] = out["refund"] > 0
    out["refund_amount"] = out["refund"]
    out["payout_amount"] = out["payout"]
    return out


def _zero_out_non_selected_accounting(
    full_candidate_with_accounting: pd.DataFrame,  # type: ignore[name-defined]
) -> pd.DataFrame:  # type: ignore[name-defined]
    """MEDIUM cycle-3: ``selected_flag=False`` 行の stake/effective_stake/payout/refund/profit を 0 にする。

    ``determine_stake_payout`` は ``is_fukusho_sale_available`` で分岐するが ``selected_flag`` 分岐を
    持たないため・購入されない non-selected (selected_flag=False) の normal 馬にも stake=100 /
    effective_stake=100 / profit が付与されてしまう。永続化前にこれらをゼロ化する。
    """
    out = full_candidate_with_accounting.copy()
    zero_cols = ["stake", "effective_stake", "payout", "refund", "profit"]
    zero_cols = [c for c in zero_cols if c in out.columns]
    non_selected_mask = out["selected_flag"].fillna(False).astype(bool) == False
    if non_selected_mask.any():
        out.loc[non_selected_mask, zero_cols] = 0
    return out


# ---------------------------------------------------------------------------
# _run_main_model_backtest — 1 backtest (BT窓 × policy × model_type)
# ---------------------------------------------------------------------------
def _run_main_model_backtest(
    bt: BTWindow,
    policy: str,
    model_type: str,
    *,
    pred_df: pd.DataFrame,  # type: ignore[name-defined]
    jodds_df: pd.DataFrame,  # type: ignore[name-defined]
    label_df: pd.DataFrame,  # type: ignore[name-defined]
    harai_race_df: pd.DataFrame,  # type: ignore[name-defined]
    feature_snapshot_id: str,
    model_version: str,
    periods: dict[str, tuple[str, str]],
    write_cur=None,
    reader_role: str | None = None,
    no_write_db: bool = False,
) -> dict[str, Any]:
    """主モデル1 backtest を実行する (EV → select → refund → metrics → load)。"""
    import pandas as pd

    from src.db.backtest_load import load_backtest

    backtest_id = f"{bt.name}-{policy}-{model_type}"

    # --- HIGH-1: 馬単位 race_times 構築 ---
    race_times = _build_race_times_per_horse(pred_df)

    # --- select_odds_snapshot (per-horse cutoff 以下最大 snapshot) ---
    snapshot = select_odds_snapshot(jodds_df, race_times, policy)

    # --- HIGH-2: pred_df と snapshot を (race_key, umaban) で merge + 行数不変 assert ---
    pred_with_odds = pred_df.merge(
        snapshot, on=["race_key", "umaban"], how="left", suffixes=("", "_snap")
    )
    if len(pred_with_odds) != len(pred_df):
        raise RuntimeError(
            f"HIGH-2 cartesian duplication 検出: backtest_id={backtest_id} "
            f"len(pred_with_odds)={len(pred_with_odds)} != len(pred_df)={len(pred_df)} "
            "(snapshot が馬単位でない・race_key 単独 JOIN 等)"
        )

    # --- HIGH-C cycle-2: HARAI race-level merge (validate='many_to_one') ---
    # CR-03: HARAI merge を compute_ev_and_rank / select_bets の前に実行。
    harai_cols = [c for c in harai_race_df.columns if c != "race_key"]
    pred_with_harai = pred_with_odds.merge(
        harai_race_df[["race_key"] + harai_cols],
        on=["race_key"],
        how="left",
        validate="many_to_one",
    )
    if len(pred_with_harai) != len(pred_with_odds):
        raise RuntimeError(
            f"HIGH-C cycle-2 HARAI broadcast 膨張検出: backtest_id={backtest_id} "
            f"len(before)={len(pred_with_odds)} != len(after)={len(pred_with_harai)} "
            "(HARAI race_key 単位の重複行が存在する・validate='many_to_one' 違反)"
        )

    # --- label 馬単位 merge (HIGH-2: on=['race_key','umaban']) ---
    # CR-03: label merge も select_bets の前に実行。select_bets は is_fukusho_sale_available /
    # is_model_eligible (label 由来) で事前 filter するため・merge 前だと実データで KeyError。
    # CR-06: suffixes=('_left','_label') で左側無修飾を許さず・label 系列は常に _label 付きを正とする。
    label_cols = [c for c in label_df.columns if c not in {"race_key", "umaban"}]
    full_candidate_with_label = pred_with_harai.merge(
        label_df[["race_key", "umaban"] + label_cols],
        on=["race_key", "umaban"],
        how="left",
        suffixes=("_left", "_label"),
    )
    if len(full_candidate_with_label) != len(pred_with_harai):
        raise RuntimeError(
            f"HIGH-2 label merge 行数不変違反: backtest_id={backtest_id} "
            f"len(before)={len(pred_with_harai)} != len(after)={len(full_candidate_with_label)}"
        )
    # CR-06: label 系列の同名列衝突時は _label を正とし・_left は破棄して元列名に正規化。
    # 現状の実データ pred_df (PREDICTION_COLUMNS のみ) では衝突しないが・将来の label 列混入
    # (debug join 等) で silent に誤扱いになるのを構造的に防止 (silent leak 経路の潜在リスク)。
    for col in label_cols:
        left_col = f"{col}_left"
        label_col = f"{col}_label"
        if (
            left_col in full_candidate_with_label.columns
            and label_col in full_candidate_with_label.columns
        ):
            full_candidate_with_label[col] = full_candidate_with_label[label_col]
            full_candidate_with_label = full_candidate_with_label.drop(
                columns=[left_col, label_col]
            )
        elif label_col in full_candidate_with_label.columns:
            # 左側に同名列が無かった場合は pandas は suffix を付与しないが・安全のため。
            full_candidate_with_label[col] = full_candidate_with_label[label_col]
            full_candidate_with_label = full_candidate_with_label.drop(columns=[label_col])

    # --- compute_ev_and_rank (fuku_odds_lower/upper と p_fukusho_hit のみ消費・label 系列に非依存) ---
    pred_with_ev = compute_ev_and_rank(full_candidate_with_label)

    # --- select_bets → full_candidate table 構築 (MEDIUM-A cycle-2) ---
    # CR-03: label merge 済みのため is_fukusho_sale_available / is_model_eligible が存在。
    selected = select_bets(pred_with_ev)
    full_candidate = pred_with_ev.copy()
    # selected_flag: select_bets で選ばれた馬は True・それ以外は False
    if "selected_flag" in selected.columns and len(selected) > 0:
        selected_keys = set(zip(selected["race_key"], selected["umaban"]))
        full_candidate["selected_flag"] = [
            (rk, um) in selected_keys
            for rk, um in zip(full_candidate["race_key"], full_candidate["umaban"])
        ]
    else:
        full_candidate["selected_flag"] = False
    # odds_missing_reason は snapshot 側から伝播 (no_bet/special_value/normal)
    if "odds_missing_reason" not in full_candidate.columns:
        full_candidate["odds_missing_reason"] = None

    # --- determine_stake_payout で会計付与 (行ベース slot lookup 含む) ---
    full_candidate_with_accounting = _attach_accounting(full_candidate_with_label)

    # --- MEDIUM cycle-3: non-selected 会計ゼロ化 ---
    full_candidate_with_accounting = _zero_out_non_selected_accounting(
        full_candidate_with_accounting
    )

    # --- metrics は selected_flag=True の行のみで計算 ---
    selected_rows = full_candidate_with_accounting[
        full_candidate_with_accounting["selected_flag"] == True  # noqa: E712
    ]
    metrics = compute_backtest_metrics(selected_rows)

    # --- provenance 付与 ---
    full_candidate_with_provenance = _attach_provenance(
        full_candidate_with_accounting,
        backtest_id=backtest_id,
        bt_name=bt.name,
        odds_policy=policy,
        model_type=model_type,
        model_version=model_version,
        feature_snapshot_id=feature_snapshot_id,
        periods=periods,
    )

    # --- load_backtest (full_candidate・MEDIUM-A cycle-2) ---
    checksum = "(skip --no-write-db)"
    if write_cur is not None and not no_write_db:
        checksum = load_backtest(write_cur, full_candidate_with_provenance, reader_role=reader_role)

    # --- report 行構築 ---
    selected_count = int(metrics.get("selected_count", 0))
    effective_bet = int(metrics.get("effective_bet_count", 0))
    refund_count = int(metrics.get("refund_count", 0))
    hit_count = int(metrics.get("hit_count", 0))
    hit_rate = (hit_count / effective_bet) if effective_bet > 0 else 0.0
    return {
        "backtest_id": backtest_id,
        "bt_name": bt.name,
        "odds_policy": policy,
        "model_type": model_type,
        "recovery_rate": float(metrics.get("recovery_rate", 0.0)),
        "P/L": int(metrics.get("profit_loss", 0)),
        "max_DD": int(metrics.get("max_drawdown", 0)),
        "selected": selected_count,
        "effective_bet": effective_bet,
        "refund": refund_count,
        "hit_rate": hit_rate,
        "_metrics": metrics,
        "_checksum": checksum,
        "_full_candidate_rows": len(full_candidate_with_provenance),
    }


def _run_bl3_backtest(
    bt: BTWindow,
    *,
    market_df: pd.DataFrame,  # type: ignore[name-defined]
    label_df: pd.DataFrame,  # type: ignore[name-defined]
    harai_race_df: pd.DataFrame,  # type: ignore[name-defined]
    periods: dict[str, tuple[str, str]],
    feature_snapshot_id: str,
    write_cur=None,
    reader_role: str | None = None,
    no_write_db: bool = False,
) -> dict[str, Any]:
    """BL-3 1 backtest を実行する (D-04・確定オッズ昇順 top-2)。"""
    import pandas as pd

    from src.db.backtest_load import load_backtest

    backtest_id = f"{bt.name}-{BL3_ODDS_SNAPSHOT_POLICY}-{BL3_MODEL_TYPE}"

    selected = select_bl3_bets(market_df)
    if len(selected) == 0:
        # BL-3 候補無し (market データ無し等) → 空メトリクス
        return {
            "backtest_id": backtest_id,
            "bt_name": bt.name,
            "odds_policy": BL3_ODDS_SNAPSHOT_POLICY,
            "model_type": BL3_MODEL_TYPE,
            "recovery_rate": 0.0,
            "P/L": 0,
            "max_DD": 0,
            "selected": 0,
            "effective_bet": 0,
            "refund": 0,
            "hit_rate": 0.0,
            "_metrics": {},
            "_checksum": "(skip)",
            "_full_candidate_rows": 0,
        }

    # full_candidate (BL-3 は主モデルと異なり EV 列を持たない)
    full_candidate = market_df.copy()
    # CR-04: fetch_market_data は race_date を返さないが・compute_backtest_metrics が
    # sort_values(['race_date','race_key','umaban']) を呼ぶため・label_df から race_key 単位で
    # race_date を補完 (race_date は race 単位・全馬同値のため race_key 単位 map で安全)。
    if "race_date" not in full_candidate.columns and "race_date" in label_df.columns:
        date_map = label_df.drop_duplicates("race_key")[["race_key", "race_date"]]
        full_candidate = full_candidate.merge(
            date_map, on="race_key", how="left", validate="many_to_one"
        )
    selected_keys = set(zip(selected["race_key"], selected["umaban"]))
    full_candidate["selected_flag"] = [
        (rk, um) in selected_keys
        for rk, um in zip(full_candidate["race_key"], full_candidate["umaban"])
    ]
    full_candidate["stake"] = full_candidate["selected_flag"].astype(int) * 100

    # HARAI race-level merge (HIGH-C)
    harai_cols = [c for c in harai_race_df.columns if c != "race_key"]
    full_candidate_with_harai = full_candidate.merge(
        harai_race_df[["race_key"] + harai_cols],
        on=["race_key"],
        how="left",
        validate="many_to_one",
    )

    # label 馬単位 merge
    label_cols = [c for c in label_df.columns if c not in {"race_key", "umaban"}]
    full_candidate_with_label = full_candidate_with_harai.merge(
        label_df[["race_key", "umaban"] + label_cols],
        on=["race_key", "umaban"],
        how="left",
        suffixes=("", "_label"),
    )

    accounting = full_candidate_with_label.apply(
        determine_stake_payout, axis=1, result_type="expand"
    )
    accounting.columns = ["stake", "refund", "payout", "profit", "effective_stake"]
    # _attach_accounting と同様に既存 stake 等との衝突を避けるため drop → concat
    base = full_candidate_with_label.drop(
        columns=[c for c in accounting.columns if c in full_candidate_with_label.columns],
        errors="ignore",
    )
    full_candidate_with_accounting = pd.concat([base, accounting], axis=1)
    full_candidate_with_accounting["refund_flag"] = (
        full_candidate_with_accounting["refund"] > 0
    )
    full_candidate_with_accounting["refund_amount"] = full_candidate_with_accounting["refund"]
    full_candidate_with_accounting["payout_amount"] = full_candidate_with_accounting["payout"]
    # MEDIUM cycle-3 non-selected ゼロ化
    full_candidate_with_accounting = _zero_out_non_selected_accounting(
        full_candidate_with_accounting
    )

    selected_rows = full_candidate_with_accounting[full_candidate_with_accounting["selected_flag"] == True]  # noqa: E712
    metrics = compute_backtest_metrics(selected_rows)

    # BL-3 provenance (EV 列は持たない・D-04)
    full_candidate_with_provenance = _attach_provenance(
        full_candidate_with_accounting,
        backtest_id=backtest_id,
        bt_name=bt.name,
        odds_policy=BL3_ODDS_SNAPSHOT_POLICY,
        model_type=BL3_MODEL_TYPE,
        model_version=f"{feature_snapshot_id}-bl3-v1",
        feature_snapshot_id=feature_snapshot_id,
        periods=periods,
    )
    # BL-3 は odds_snapshot_at / odds_source_type を confirmed sentinel で埋める
    full_candidate_with_provenance["odds_snapshot_at"] = pd.NaT
    full_candidate_with_provenance["odds_source_type"] = "confirmed"
    if "EV_lower" not in full_candidate_with_provenance.columns:
        full_candidate_with_provenance["EV_lower"] = None
        full_candidate_with_provenance["EV_upper"] = None

    checksum = "(skip --no-write-db)"
    if write_cur is not None and not no_write_db:
        checksum = load_backtest(write_cur, full_candidate_with_provenance, reader_role=reader_role)

    selected_count = int(metrics.get("selected_count", 0))
    effective_bet = int(metrics.get("effective_bet_count", 0))
    refund_count = int(metrics.get("refund_count", 0))
    hit_count = int(metrics.get("hit_count", 0))
    hit_rate = (hit_count / effective_bet) if effective_bet > 0 else 0.0
    return {
        "backtest_id": backtest_id,
        "bt_name": bt.name,
        "odds_policy": BL3_ODDS_SNAPSHOT_POLICY,
        "model_type": BL3_MODEL_TYPE,
        "recovery_rate": float(metrics.get("recovery_rate", 0.0)),
        "P/L": int(metrics.get("profit_loss", 0)),
        "max_DD": int(metrics.get("max_drawdown", 0)),
        "selected": selected_count,
        "effective_bet": effective_bet,
        "refund": refund_count,
        "hit_rate": hit_rate,
        "_metrics": metrics,
        "_checksum": checksum,
        "_full_candidate_rows": len(full_candidate_with_provenance),
    }


# ---------------------------------------------------------------------------
# _assert_jodds_coverage_horse_level — MEDIUM-B cycle-2 gate
# ---------------------------------------------------------------------------
def _assert_jodds_coverage_horse_level(
    bt: BTWindow,
    policy: str,
    pred_df: pd.DataFrame,  # type: ignore[name-defined]
    snapshot: pd.DataFrame,  # type: ignore[name-defined]
    *,
    threshold: float = JODDS_HORSE_COVERAGE_THRESHOLD,
    race_threshold: float = JODDS_RACE_COVERAGE_THRESHOLD,
) -> dict[str, Any]:
    """BT窓 test の candidate-horse usable-odds coverage を測定し閾値未満で loud fail する (MEDIUM-B)。

    horse-level usable-odds coverage = (no_bet sentinel を除いた実利用可能オッズ馬の割合)。
    race-level coverage は secondary check (元 MEDIUM-05)。

    Parameters
    ----------
    snapshot : pd.DataFrame
        ``select_odds_snapshot`` の戻り値 (race_key/umaban/fuku_odds_lower/odds_missing_reason を持つ)。
    pred_df : pd.DataFrame
        BT窓 test 予測馬 (race_key/umaban を持つ)。

    Returns
    -------
    dict
        ``{bt_name, policy, horse_level_coverage, race_level_coverage, threshold, status}``

    Raises
    ------
    RuntimeError
        horse-level coverage < threshold または race-level coverage < race_threshold の時。
    """
    no_bet_reasons = {"no_bet", "no_bet_empty", "special_value", "fukusyoflag_not_normal_sale"}
    if "odds_missing_reason" in snapshot.columns:
        usable_mask = ~snapshot["odds_missing_reason"].fillna("__ok__").isin(no_bet_reasons)
    else:
        usable_mask = snapshot["fuku_odds_lower"].notna()
    usable_horses = int(usable_mask.sum())
    total_horses = max(int(len(snapshot)), 1)
    horse_level_coverage = usable_horses / total_horses

    # race-level coverage: snapshot が存在する race_key の割合
    snapshot_races = set(snapshot.loc[usable_mask, "race_key"]) if "race_key" in snapshot.columns else set()
    total_races = max(pred_df["race_key"].nunique(), 1) if "race_key" in pred_df.columns else 1
    race_level_coverage = len(snapshot_races) / total_races

    status = "pass"
    if horse_level_coverage < threshold:
        status = "fail_horse_level"
        raise RuntimeError(
            f"MEDIUM-B horse-level usable-odds coverage {horse_level_coverage:.2%} < threshold "
            f"{threshold:.2%} for {bt.name}/{policy}: 多数馬が no_bet/special-odds・取得未完か"
            "発売異常の可能性。--synthetic を除く実行は不可。"
        )
    if race_level_coverage < race_threshold:
        status = "fail_race_level"
        raise RuntimeError(
            f"MEDIUM-05 race-level JODDS coverage {race_level_coverage:.2%} < threshold "
            f"{race_threshold:.2%} for {bt.name}/{policy}"
        )
    return {
        "bt_name": bt.name,
        "policy": policy,
        "horse_level_coverage": horse_level_coverage,
        "race_level_coverage": race_level_coverage,
        "threshold": threshold,
        "race_threshold": race_threshold,
        "status": status,
        "usable_horses": usable_horses,
        "total_horses": total_horses,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Phase 5 フル行列 backtest pipeline を実行する。"""
    args = parse_args(argv)
    settings = Settings()

    # T-05-17 / Shared Pattern 8: 生 DSN は絶対に出力しない (masked のみ)
    logger.info("readonly DSN: %s", settings.dsn_masked)
    logger.info("etl      DSN: %s", settings.etl_dsn_masked)
    logger.info(
        "config: snapshot_id=%s synthetic=%s bt_filter=%s check_reproduce=%s write_db=%s",
        args.snapshot_id,
        args.synthetic,
        args.bt_filter,
        args.check_reproduce,
        not args.no_write_db,
    )

    bt_windows = _select_bt_windows(args.bt_filter)
    logger.info("BT windows: %s", [bt.name for bt in bt_windows])

    readonly_pool = None if args.synthetic else make_pool(settings, role="readonly")
    etl_pool = (
        None
        if (args.synthetic or args.no_write_db)
        else make_pool(settings, role="etl")
    )

    try:
        return _run_pipeline(
            args=args,
            settings=settings,
            bt_windows=bt_windows,
            readonly_pool=readonly_pool,
            etl_pool=etl_pool,
        )
    except PsycopgError as e:
        logger.error("DB error: %s", e)
        return 3
    finally:
        if readonly_pool is not None:
            readonly_pool.close()
        if etl_pool is not None:
            etl_pool.close()


def _run_pipeline(
    *,
    args: argparse.Namespace,
    settings: Settings,
    bt_windows: list[BTWindow],
    readonly_pool,
    etl_pool,
) -> int:
    """pipeline 本体 (main から分離・test から直接呼出可能)。"""
    import pandas as pd

    all_backtests: list[dict[str, Any]] = []
    coverage_summary: list[dict[str, Any]] = []

    # --- --check-reproduce: SC#4 bit-identical 検証のみ ---
    if args.check_reproduce:
        logger.info("SC#4 reproduce smoke: 開始 (BT窓毎に bit-identical 検証)")
        feature_df = _prepare_feature_df(args, readonly_pool)
        for bt in bt_windows:
            periods = _carve_calib_from_train_tail(bt)
            bt_map = _fit_bt_category_map(feature_df, periods["train"][0], periods["train"][1])
            for mt in ALL_MODEL_TYPES:
                _assert_deterministic(
                    mt,
                    feature_df,
                    feature_snapshot_id=args.snapshot_id,
                    version_n=args.version_n,
                    seed=42,
                    as_of_datetime=FIXED_REPRODUCE_TS,
                    split_periods=periods,
                    category_map=bt_map,
                )
                logger.info(
                    "SC#4 PASS: %s/%s (BT窓 periods + category_map で bit-identical)",
                    bt.name,
                    mt,
                )
        logger.info("SC#4 reproduce smoke: 全 BT窓 PASS")

    # --- データ準備 ---
    # 合成データの場合は pred_df / jodds / label / harai を合成 (train_and_predict を呼ばない)
    # 実データの場合は BT窓再学習ループで train_and_predict を呼び pred_df を得る
    is_synthetic = bool(args.synthetic)

    # --- BT窓ループ ---
    for bt in bt_windows:
        periods = _carve_calib_from_train_tail(bt)
        logger.info(
            "BT窓 %s: periods train=%s..%s calib=%s..%s test=%s..%s",
            bt.name,
            periods["train"][0], periods["train"][1],
            periods["calib"][0], periods["calib"][1],
            periods["test"][0], periods["test"][1],
        )

        if is_synthetic:
            # 合成データ: BT窓 test 期間の feature_df 抽出
            feature_df = _build_synthetic_feature_df()
            feature_df_test = feature_df[
                feature_df["race_date"].between(periods["test"][0], periods["test"][1])
            ].copy()
            pred_df = _build_synthetic_pred_df(feature_df_test)
            jodds_df = _build_synthetic_jodds_df(feature_df_test)
            label_df = _build_synthetic_label_df(feature_df_test)
            harai_race_df = _build_synthetic_harai_df(feature_df_test)
            market_df = _build_synthetic_market_df(feature_df_test)
            model_version_by_type = {mt: f"{args.snapshot_id}-{mt}-v1" for mt in ALL_MODEL_TYPES}
        else:
            # 実データ: BT窓再学習ループ (D-03)
            feature_df = _prepare_feature_df(args, readonly_pool)
            # HIGH-5: BT窓 train 期間のみで fit_category_map
            bt_map = _fit_bt_category_map(
                feature_df, periods["train"][0], periods["train"][1]
            )
            pred_df_by_model: dict[str, pd.DataFrame] = {}
            model_version_by_type = {}
            for mt in ALL_MODEL_TYPES:
                logger.info("BT窓 %s train_and_predict 開始: model_type=%s", bt.name, mt)
                result = train_and_predict(
                    feature_df,
                    model_type=mt,
                    feature_snapshot_id=args.snapshot_id,
                    version_n=args.version_n,
                    seed=42,
                    as_of_datetime=FIXED_REPRODUCE_TS,
                    split_periods=periods,
                    category_map=bt_map,
                )
                pred_df_by_model[mt] = result["pred_df"]
                model_version_by_type[mt] = result["model_version"]
                logger.info(
                    "BT窓 %s train_and_predict 完了: model_type=%s pred_rows=%d category_map_source=%s",
                    bt.name, mt, len(result["pred_df"]), result.get("category_map_source"),
                )
            # JODDS / label / HARAI 取得 (readonly)
            with readonly_cursor(readonly_pool) as cur:
                jodds_df = fetch_jodds(cur)
                label_df = load_labels(cur)
                market_df = fetch_market_data(cur)
                harai_race_df = _fetch_harai_race_level(cur)
            # CR-02: load_labels は race_key を SELECT しないため・make_race_key で正準形式を付与。
            # 後続の _run_main_model_backtest / _run_bl3_backtest が label_df[['race_key','umaban']]
            # で merge を試みるため・実データパスで KeyError になる silent 障害を防止。
            if "race_key" not in label_df.columns:
                from src.model.data import make_race_key

                label_df = label_df.copy()
                label_df["race_key"] = make_race_key(label_df).to_numpy()
            # CR-04: fetch_market_data は race_key / is_fukusho_sale_available を返さないため・
            # make_race_key で race_key を付与し・is_fukusho_sale_available は label_df から
            # (race_key, umaban) 単位で補完 (BL-3 select_bl3_bets が事前 filter で必要)。
            if "race_key" not in market_df.columns:
                from src.model.data import make_race_key

                market_df = market_df.copy()
                market_df["race_key"] = make_race_key(market_df).to_numpy()
            if (
                "is_fukusho_sale_available" not in market_df.columns
                and "is_fukusho_sale_available" in label_df.columns
            ):
                sale_map = label_df.drop_duplicates("race_key")[
                    ["race_key", "is_fukusho_sale_available"]
                ]
                market_df = market_df.merge(
                    sale_map, on="race_key", how="left", validate="many_to_one"
                )
            # label を馬単位に filter (BT窓 test 期間)
            label_df = _filter_label_by_period(label_df, periods["test"][0], periods["test"][1])

        # --- 主モデル: 5窓 × 2policy × 2model ---
        for policy in ALL_POLICIES:
            # MEDIUM-B coverage gate (synthetic は skip)
            if not is_synthetic:
                race_times = _build_race_times_per_horse(pred_df_by_model[ALL_MODEL_TYPES[0]])
                snapshot_for_cov = select_odds_snapshot(jodds_df, race_times, policy)
                cov = _assert_jodds_coverage_horse_level(
                    bt, policy, pred_df_by_model[ALL_MODEL_TYPES[0]], snapshot_for_cov
                )
                coverage_summary.append(cov)
                logger.info(
                    "coverage %s/%s: horse=%.2f%% race=%.2f%% [%s]",
                    bt.name, policy,
                    cov["horse_level_coverage"] * 100, cov["race_level_coverage"] * 100, cov["status"],
                )

            for mt in ALL_MODEL_TYPES:
                if is_synthetic:
                    pred_df_this = pred_df
                else:
                    pred_df_this = pred_df_by_model[mt]

                # write_cur を backtest_id 毎に取得 (idempotent load)
                write_cur_ctx = None
                if etl_pool is not None:
                    write_cur_ctx = etl_pool.connection().__enter__().cursor().__enter__()

                try:
                    row = _run_main_model_backtest(
                        bt, policy, mt,
                        pred_df=pred_df_this,
                        jodds_df=jodds_df,
                        label_df=label_df,
                        harai_race_df=harai_race_df,
                        feature_snapshot_id=args.snapshot_id,
                        model_version=model_version_by_type[mt],
                        periods=periods,
                        write_cur=write_cur_ctx,
                        reader_role=settings.db_reader_role,
                        no_write_db=(etl_pool is None),
                    )
                finally:
                    if write_cur_ctx is not None:
                        try:
                            write_cur_ctx.__exit__(None, None, None)
                            etl_pool.connection().__exit__(None, None, None)
                        except Exception:  # noqa: BLE001
                            pass

                all_backtests.append(row)
                logger.info(
                    "backtest %s: recovery=%.4f P/L=%d max_DD=%d selected=%d checksum=%s",
                    row["backtest_id"], row["recovery_rate"], row["P/L"], row["max_DD"],
                    row["selected"], row["_checksum"],
                )

        # --- BL-3: 5窓 × 1 (D-04) ---
        write_cur_ctx = None
        if etl_pool is not None:
            write_cur_ctx = etl_pool.connection().__enter__().cursor().__enter__()
        try:
            bl3_row = _run_bl3_backtest(
                bt,
                market_df=market_df,
                label_df=label_df,
                harai_race_df=harai_race_df,
                periods=periods,
                feature_snapshot_id=args.snapshot_id,
                write_cur=write_cur_ctx,
                reader_role=settings.db_reader_role,
                no_write_db=(etl_pool is None),
            )
        finally:
            if write_cur_ctx is not None:
                try:
                    write_cur_ctx.__exit__(None, None, None)
                    etl_pool.connection().__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
        all_backtests.append(bl3_row)
        logger.info(
            "BL-3 backtest %s: recovery=%.4f P/L=%d selected=%d",
            bl3_row["backtest_id"], bl3_row["recovery_rate"], bl3_row["P/L"], bl3_row["selected"],
        )

    # --- reports 生成 (BACK-04) ---
    jodds_status = "synthetic" if is_synthetic else ("complete" if coverage_summary else "synthetic")
    md_path, json_path = generate_report(
        all_backtests,
        output_dir=args.output_dir,
        jodds_status=jodds_status,
        coverage_summary=coverage_summary if coverage_summary else None,
    )
    logger.info("reports generated: %s, %s", md_path, json_path)
    logger.info(
        "SUMMARY: 全 backtest 行=%d (主モデル %d + BL-3 %d)",
        len(all_backtests),
        sum(1 for r in all_backtests if r["model_type"] != BL3_MODEL_TYPE),
        sum(1 for r in all_backtests if r["model_type"] == BL3_MODEL_TYPE),
    )
    return 0


# ---------------------------------------------------------------------------
# helpers (実データ取得)
# ---------------------------------------------------------------------------
def _prepare_feature_df(args: argparse.Namespace, readonly_pool) -> pd.DataFrame:  # type: ignore[name-defined]
    """``load_feature_matrix`` + ``load_labels`` + ``build_training_frame`` で label-joined
    feature_df を構築する (run_train_predict.py パターン)。
    """
    feature_df_raw = load_feature_matrix()
    if readonly_pool is None:
        return feature_df_raw
    with readonly_cursor(readonly_pool) as cur:
        label_df = load_labels(cur)
    return build_training_frame(feature_df_raw, label_df)


def _build_synthetic_market_df(feature_df_test: pd.DataFrame) -> pd.DataFrame:  # type: ignore[name-defined]
    """``--synthetic`` 用の市場データ (BL-3 用・確定オッズ) を構築する。

    ``compute_backtest_metrics`` が race_date を消費するため・``race_date`` 列も保持する。
    """
    out = feature_df_test[
        ["race_key", "umaban", "race_date", "is_fukusho_sale_available"]
    ].copy()
    # fukuoddslow: 人気順 (umaban 昇順でオッズ低下)
    out["fukuoddslow"] = 1.5 + 0.3 * (out["umaban"] - 1)
    return out


def _fetch_harai_race_level(readonly_cur) -> pd.DataFrame:  # type: ignore[name-defined]
    """``raw_everydb2.n_harai`` から race-level 払戻 slot を SELECT する (HIGH-C cycle-2)。

    HARAI は race-level slot レコード (``PayFukusyoUmaban1..5`` + ``PayFukusyoPay1..5``) で・
    umaban 列を持たない。``run_backtest`` は race-level のまま予測馬行に broadcast する。
    """
    query = """
        SELECT
            year, jyocd, kaiji, nichiji, racenum,
            fuseirituflag2, henkanflag2, tokubaraiflag2,
            payfukusyoumaban1, payfukusyoumaban2, payfukusyoumaban3,
            payfukusyoumaban4, payfukusyoumaban5,
            payfukusyopay1, payfukusyopay2, payfukusyopay3,
            payfukusyopay4, payfukusyopay5
        FROM raw_everydb2.n_harai
    """
    readonly_cur.execute(query)
    cols = [d.name for d in readonly_cur.description]
    rows = readonly_cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    # race_key 構築 (CR-01): make_race_key 正準形式で単一 source of truth 化。
    # fetch_jodds / fetch_market_data の暗黙 race_key と同一形式 (5要素)。
    from src.model.data import make_race_key

    df["race_key"] = make_race_key(df).to_numpy()
    return df


def _filter_label_by_period(
    label_df: pd.DataFrame,  # type: ignore[name-defined]
    start: str,
    end: str,
) -> pd.DataFrame:  # type: ignore[name-defined]
    """label_df を test 期間で filter する (race_date があれば)。

    CR-07 / WR-05: silent fallback (空結果時に未 filter の全体を返す) を廃止し・
    fail-loud 化。空結果は BT窓 test 期間外のラベルまで backtest 対象になる silent leak
    経路 (§19.1 聖域違反・CLAUDE.md が禁止する silent fallback) になるため ValueError。
    また between 前に pd.to_datetime で型を正規化し・文字列 / date / Timestamp 混在で
    境界日が silent に欠損 / 重複するリスクを排除。
    """
    if "race_date" not in label_df.columns:
        return label_df
    # 型正規化 (文字列・date・Timestamp 混在を統一)
    out = label_df.copy()
    out["race_date"] = pd.to_datetime(out["race_date"], errors="coerce")
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    mask = out["race_date"].between(start_ts, end_ts)
    filtered = out.loc[mask].copy()
    if len(filtered) == 0:
        raise ValueError(
            f"_filter_label_by_period: test 期間 ({start}..{end}) に該当する label 行が0件 "
            "(silent フォールバック禁止・race_date 型または BT窓区間を確認・§19.1 聖域)"
        )
    return filtered


if __name__ == "__main__":
    sys.exit(main())
