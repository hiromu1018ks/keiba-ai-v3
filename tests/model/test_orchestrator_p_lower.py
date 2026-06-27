# ruff: noqa: E501  (長い docstring を保持するため行長は緩和)
"""Phase 12 Plan 02 Task 1: orchestrator L754 後 p_lower 生成 + q_shrink test 窓外部注入 API
+ return dict provenance + artifact metadata allow_nan=False 検証契約 (EV-01・§11.2・§19.1).

本テストは 12-02-PLAN.md Task 1 で新設する。test_orchestrator.py (Phase 4) ・
test_race_relative.py (Phase 11) と併用し・Phase 12 SC#1 p_lower 生成経路の機械保証を行う。

検証内容 (PLAN Task 1 behavior Test 1-12):
- Test 1 (§11.2 聖域・calib slice のみ): train_and_predict(score_split='calib') が
  calib slice の pred_proba と y_calib のみで q_shrink を計算 (test 窓 outcome を取らない)
- Test 2 (theta=None で NULL): theta=None 呼出 (v1.0 binary) で pred_df['p_fukusho_hit_lower'] が全て None/NaN
- Test 3 (theta 指定で p_lower 付与): theta=1.0 呼出で pred_df['p_fukusho_hit_lower'] が非 NULL かつ p_lower <= p_fukusho_hit
- Test 4 (byte-reproducible): theta=1.0 で2回 train_and_predict を呼び p_fukusho_hit_lower 列が np.array_equal
- Test 5 (return dict provenance): return dict に p_lower_q_level=0.90・p_lower_q_shrink=float・p_lower_shrinkage_method が含まれる
- Test 6 (artifact metadata): save_native_artifact で metadata.json に3キーが記録される
- Test 7 (silent fallback 禁止): pred_proba_lower と pred_proba の index/長さ不整合で RuntimeError
- Test 8 (C-12-02-1 HIGH・q_shrink 外部注入 API signature): inspect.signature の parameters に
  p_lower_q_shrink: float | None = None と p_lower_q_level: float = 0.90 が KEYWORD_ONLY で含まれる
- Test 9 (C-12-02-1 HIGH・q_shrink test 窓 fail-loud): score_split='test', theta=1.0, p_lower_q_shrink=None で RuntimeError
- Test 10 (C-12-02-1 HIGH・q_shrink 外部注入で p_lower 生成): score_split='test', theta=1.0,
  p_lower_q_shrink=<calibで計算した値> で pred_df['p_fukusho_hit_lower'] が非 NULL かつ p_lower <= p_fukusho_hit
- Test 11 (C-12-02-2・predict_p_fukusho pred_proba_lower 引数): inspect.signature に pred_proba_lower が含まれる・
  None の場合 p_fukusho_hit_lower 列が NULL
- Test 12 (C-12-02-5・artifact allow_nan=False): artifact.py の metadata JSON 書き出しが allow_nan=False を呼び
  NaN を含む dict で ValueError/TypeError で fail-loud

参考: 12-02-PLAN.md / 12-CONTEXT.md / 12-RESEARCH.md Pattern 1 / 12-PATTERNS.md orchestrator・artifact /
      12-REVIEWS.md C-12-02-1 HIGH・C-12-02-2・C-12-02-5 / src/model/orchestrator.py L714-754 /
      src/model/race_relative.py compute_p_lower_conformal_shrinkage.
"""

from __future__ import annotations

import inspect
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.model.artifact import save_native_artifact, write_metadata_json
from src.model.orchestrator import (
    FIXED_REPRODUCE_TS,
    train_and_predict,
)
from src.model.predict import predict_p_fukusho
from src.model.race_relative import compute_p_lower_conformal_shrinkage


# ---------------------------------------------------------------------------
# 共通 helper: 合成 label-joined feature_df (race-relative model 実行可能・sales_start_entry_count 含む)
# ---------------------------------------------------------------------------
# test_orchestrator.py の _build_label_joined_feature_df を踏襲しつつ・Phase 12 は
# sales_start_entry_count 列を含める (race_relative 適用に必須・orchestrator L715 で RuntimeError になる).
# train/calib/test の3区間にまたがる race_date を持つ. 8頭立て (k=3).

def _build_label_joined_feature_df_with_entry_count(
    n_train_races: int = 80,
    n_calib_races: int = 30,
    n_test_races: int = 30,
    n_holdout_races: int = 12,
    seed: int = 42,
) -> pd.DataFrame:
    """split_3way の3区間 + holdout_2025_plus にまたがる label-joined feature_df を構築する.

    Phase 12 拡張: sales_start_entry_count 列を含む (race_relative 補正に必須・8頭固定で k=3).
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []

    def _add_period(n_races: int, start: str, end: str, period_seed_offset: int) -> None:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        span_days = max(1, (end_ts - start_ts).days)
        for race_i in range(n_races):
            race_dt = start_ts + pd.Timedelta(days=int(span_days * race_i / max(1, n_races)))
            jyocd = (race_i % 10) + 1
            kaiji = ((race_i // 10) % 8) + 1
            nichiji = ((race_i // 80) % 12) + 1
            racenum = jyocd
            race_key = (
                f"{race_dt.year}-{jyocd:02d}-{kaiji:02d}-"
                f"{nichiji:02d}-{racenum}-p{period_seed_offset}-r{race_i}"
            )
            for umaban in range(1, 9):
                rows.append(
                    {
                        "race_start_datetime": race_dt,
                        "race_key": race_key,
                        "race_date": race_dt.normalize(),
                        "year": race_dt.year,
                        "jyocd": f"{jyocd:02d}",
                        "kaiji": kaiji,
                        "nichiji": f"{nichiji:02d}",
                        "racenum": racenum,
                        "umaban": umaban,
                        "kettonum": int(rng.integers(1, 100_000_000)),
                        # Phase 12: race-relative 補正に必須 (orchestrator L715 で RuntimeError にならないよう)
                        "sales_start_entry_count": 8,
                        "sexcd": str(int(rng.choice([1, 2, 3]))),
                        "class_code_normalized": str(int(rng.choice([703, 701, 5, 10, 999]))),
                        "estimated_running_style": str(int(rng.choice([1, 2, 3, 4, 5]))),
                        "rolling_jyocd_mode_5": str(int(rng.choice([5, 6, 7, 8, 9]))),
                        "rolling_jyocd_latest_5": str(int(rng.choice([5, 6, 7, 8, 9]))),
                        "jockey_id_code": np.int32(rng.integers(0, 100)),
                        "trainer_id_code": np.int32(rng.integers(0, 80)),
                        "sire_id_code": np.int32(rng.integers(0, 500)),
                        "bms_id_code": np.int32(rng.integers(0, 500)),
                        "horse_id_code": np.int32(rng.integers(0, 2000)),
                        "barei": int(rng.integers(2, 9)),
                        "futan": int(rng.integers(48, 58)),
                        "wakuban": int(rng.integers(1, 9)),
                        "rolling_babacd_latest_5": float(rng.normal(0.5, 0.1)),
                        "rolling_babacd_mean_5": float(rng.normal(0.5, 0.1)),
                        "rolling_babacd_sd_5": float(rng.normal(0.05, 0.01)),
                        "rolling_days_since_prev_latest_5": int(rng.integers(7, 60)),
                        "rolling_days_since_prev_mean_5": float(rng.normal(30.0, 5.0)),
                        "rolling_days_since_prev_sd_5": float(rng.normal(10.0, 2.0)),
                        "rolling_harontimel3_latest_5": float(rng.normal(35.0, 1.0)),
                        "rolling_harontimel3_mean_5": float(rng.normal(35.0, 1.0)),
                        "rolling_harontimel3_sd_5": float(rng.normal(0.5, 0.1)),
                        "rolling_jyuni3c_jyuni4c_latest_5": float(rng.normal(5.0, 2.0)),
                        "rolling_jyuni3c_jyuni4c_mean_5": float(rng.normal(5.0, 2.0)),
                        "rolling_jyuni3c_jyuni4c_sd_5": float(rng.normal(2.0, 0.5)),
                        "rolling_kakuteijyuni_latest_5": float(rng.normal(5.0, 2.0)),
                        "rolling_kakuteijyuni_mean_5": float(rng.normal(5.0, 2.0)),
                        "rolling_kakuteijyuni_sd_5": float(rng.normal(2.0, 0.5)),
                        "rolling_kyori_latest_5": int(rng.choice([1400, 1600, 1800, 2000])),
                        "rolling_kyori_mean_5": float(rng.normal(1800.0, 100.0)),
                        "rolling_kyori_sd_5": float(rng.normal(100.0, 20.0)),
                        "rolling_timediff_latest_5": float(rng.normal(0.0, 0.5)),
                        "rolling_timediff_mean_5": float(rng.normal(0.0, 0.3)),
                        "rolling_timediff_sd_5": float(rng.normal(0.3, 0.05)),
                        "is_model_eligible": True,
                        "label_validation_status": "ok",
                        "fukusho_hit_validated": int(rng.random() < 0.21),
                    }
                )

    _add_period(n_train_races, "2016-07-01", "2023-12-31", 0)
    _add_period(n_calib_races, "2024-01-01", "2024-06-30", 1)
    _add_period(n_test_races, "2024-07-01", "2024-12-31", 2)
    _add_period(n_holdout_races, "2025-01-01", "2025-12-31", 3)

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["race_start_datetime", "race_key", "umaban"], kind="mergesort"
    ).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Test 8: [C-12-02-1 / HIGH] q_shrink 外部注入 API・signature (keyword-only)
# ---------------------------------------------------------------------------
def test_train_and_predict_p_lower_signature_keyword_only():
    """[C-12-02-1 HIGH] train_and_predict の signature に p_lower_q_shrink・p_lower_q_level が
    keyword-only で存在する (§11.2 聖域の外部注入 API・構造的機械保証)."""
    sig = inspect.signature(train_and_predict)
    assert "p_lower_q_shrink" in sig.parameters, (
        "train_and_predict に p_lower_q_shrink keyword-only 引数がない (C-12-02-1 HIGH)"
    )
    assert "p_lower_q_level" in sig.parameters, (
        "train_and_predict に p_lower_q_level keyword-only 引数がない (C-12-02-1 HIGH)"
    )
    assert sig.parameters["p_lower_q_shrink"].kind == inspect.Parameter.KEYWORD_ONLY, (
        "p_lower_q_shrink は keyword-only であること (C-12-02-1 HIGH)"
    )
    assert sig.parameters["p_lower_q_level"].kind == inspect.Parameter.KEYWORD_ONLY, (
        "p_lower_q_level は keyword-only であること (C-12-02-1 HIGH)"
    )
    # 既定値: p_lower_q_shrink=None (外部注入なし)・p_lower_q_level=0.90 (D-02 事前登録値)
    assert sig.parameters["p_lower_q_shrink"].default is None
    assert sig.parameters["p_lower_q_level"].default == 0.90


# ---------------------------------------------------------------------------
# Test 11: [C-12-02-2 / MEDIUM] predict_p_fukusho pred_proba_lower 引数
# ---------------------------------------------------------------------------
def test_predict_p_fukusho_pred_proba_lower_signature():
    """[C-12-02-2 MEDIUM] predict_p_fukusho の signature に pred_proba_lower が含まれる."""
    sig = inspect.signature(predict_p_fukusho)
    assert "pred_proba_lower" in sig.parameters, (
        "predict_p_fukusho に pred_proba_lower 引数がない (C-12-02-2 MEDIUM)"
    )
    # Plan 01 で追加済み・None 既定値 (v1.0 binary 呼出互換)
    assert sig.parameters["pred_proba_lower"].default is None


# ---------------------------------------------------------------------------
# Test 12: [C-12-02-5 / MEDIUM] artifact.py の metadata JSON が allow_nan=False で厳密化
# ---------------------------------------------------------------------------
def test_artifact_metadata_json_allow_nan_false_strict():
    """[C-12-02-5 MEDIUM] artifact.py の metadata JSON 書き出しが allow_nan=False を使用し・
    NaN を含む dict で fail-loud する (§19.1・RFC 8259 strict)."""
    # ソースコードで allow_nan=False が使われていることを確認 (grep ベースの機械保証).
    import src.model.artifact as artifact_mod

    src = inspect.getsource(artifact_mod)
    assert "allow_nan=False" in src, (
        "artifact.py の JSON 書き出しに allow_nan=False がない (C-12-02-5 MEDIUM・§19.1 厳密性)"
    )

    # 実挙動検証: NaN を含む dict を渡すと ValueError/TypeError で fail-loud する.
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "meta"
        nan_dict = {"q_shrink": float("nan"), "model_version": "v1"}
        with pytest.raises((ValueError, TypeError)):
            write_metadata_json(out_dir, nan_dict)


# ===========================================================================
# Test 9: [C-12-02-1 / HIGH] q_shrink test 窓 fail-loud
# (score_split='test', theta=1.0, p_lower_q_shrink=None → RuntimeError)
# ===========================================================================
def test_q_shrink_test_window_fail_loud_without_injection():
    """[C-12-02-1 HIGH] score_split='test' で theta is not None かつ p_lower_q_shrink is None の場合・
    test 窓で q_shrink を再計算する経路に滑るのを RuntimeError で構造的に阻止 (§11.2 聖域)."""
    feature_df = _build_label_joined_feature_df_with_entry_count()
    with pytest.raises(RuntimeError, match=r"p_lower_q_shrink.*§11.2|§11.2.*p_lower_q_shrink"):
        train_and_predict(
            feature_df,
            model_type="lightgbm_rr",
            feature_snapshot_id="20260627-1a-test",
            theta=1.0,
            score_split="test",
            p_lower_q_shrink=None,  # 外部注入なし → fail-loud
            as_of_datetime=FIXED_REPRODUCE_TS,
            label_version="v1.0",
            odds_snapshot_policy="30min_before",
            backtest_strategy_version="fukusho_ev_v1",
        )


# ===========================================================================
# 統合テスト群 (実際に train_and_predict を呼ぶ・DB 不要・KEIBA_SKIP_DB_TESTS=1 で GREEN)
# ===========================================================================
# 計算コストを抑えるため・上記 helper は最小の n_races で呼ぶ.

def _run_train_and_predict_minimal(**overrides):
    """最小サイズの合成 frame で train_and_predict を呼ぶ helper.

    全テストで共通の既定 kwargs を中央集権化し・test 毎の差分だけ overrides で渡す.
    """
    feature_df = _build_label_joined_feature_df_with_entry_count(
        n_train_races=60, n_calib_races=24, n_test_races=24, n_holdout_races=12
    )
    kwargs = dict(
        model_type="lightgbm_rr",
        feature_snapshot_id="20260627-1a-test",
        theta=1.0,
        score_split="calib",  # 既定は calib slice 経路 (§11.2 聖域・calib slice のみ)
        p_lower_q_level=0.90,
        as_of_datetime=FIXED_REPRODUCE_TS,
        label_version="v1.0",
        odds_snapshot_policy="30min_before",
        backtest_strategy_version="fukusho_ev_v1",
    )
    kwargs.update(overrides)
    return train_and_predict(feature_df, **kwargs)


# ---------------------------------------------------------------------------
# Test 1: (§11.2 聖域・calib slice のみ) score_split='calib' で calib slice のみ q_shrink 計算
# ---------------------------------------------------------------------------
def test_calib_slice_only_q_shrink_computation():
    """score_split='calib' 呼出で q_shrink 計算が calib slice の pred_proba と y_calib のみで行われる
    (test 窓 outcome を取らない・score_split guard L449-455 で構造的聖域ブロック済み)."""
    # score_split='calib' で呼出 → RuntimeError にならず・q_shrink が calib slice のみから計算される.
    result = _run_train_and_predict_minimal(score_split="calib")
    # return dict に p_lower provenance が含まれる (Test 5 と重複するが・聖域確認のため先取り)
    assert result["p_lower_q_shrink"] is not None
    assert isinstance(result["p_lower_q_shrink"], float)
    # score_split='calib' なので pred_df は calib slice の予測 (test 窓ではない)
    assert result["score_split"] == "calib"
    # p_fukusho_hit_lower 列が非 NULL (theta is not None・score_split='calib' 経路)
    assert result["pred_df"]["p_fukusho_hit_lower"].notna().all()


# ---------------------------------------------------------------------------
# Test 2: theta=None で NULL (v1.0 binary 呼出・後方互換・A5)
# ---------------------------------------------------------------------------
def test_theta_none_yields_null_p_lower():
    """theta=None 呼出 (v1.0 binary) で pred_df['p_fukusho_hit_lower'] が全て None/NaN (後方互換・A5)."""
    feature_df = _build_label_joined_feature_df_with_entry_count(
        n_train_races=60, n_calib_races=24, n_test_races=24, n_holdout_races=12
    )
    result = train_and_predict(
        feature_df,
        model_type="lightgbm",  # binary (race-relative でない)
        feature_snapshot_id="20260627-1a-test",
        theta=None,  # v1.0 binary
        as_of_datetime=FIXED_REPRODUCE_TS,
        label_version="v1.0",
        odds_snapshot_policy="30min_before",
        backtest_strategy_version="fukusho_ev_v1",
    )
    # theta=None なので p_fukusho_hit_lower は全行 None/NaN (後方互換・A5)
    assert result["pred_df"]["p_fukusho_hit_lower"].isna().all(), (
        "theta=None 呼出は p_fukusho_hit_lower が全行 NULL であること (A5 後方互換)"
    )
    # return dict の provenance も None (theta=None のため)
    assert result["p_lower_q_level"] is None
    assert result["p_lower_q_shrink"] is None
    assert result["p_lower_shrinkage_method"] is None


# ---------------------------------------------------------------------------
# Test 3: theta 指定で p_lower 付与 (score_split='calib' 経路)
# ---------------------------------------------------------------------------
def test_theta_specified_yields_non_null_p_lower_le_than_p():
    """theta=1.0 呼出 (score_split='calib') で pred_df['p_fukusho_hit_lower'] が非 NULL かつ
    p_lower <= p_fukusho_hit (D-01: max(0, p_final - q_shrink) <= p_final)."""
    result = _run_train_and_predict_minimal(score_split="calib")
    pred_df = result["pred_df"]
    p = pred_df["p_fukusho_hit"].to_numpy(dtype=float)
    p_lower = pred_df["p_fukusho_hit_lower"].to_numpy(dtype=float)
    # 非NULL
    assert np.all(np.isfinite(p_lower)), "p_fukusho_hit_lower は非 NULL かつ finite であること"
    # p_lower <= p_fukusho_hit (D-01)
    assert np.all(p_lower <= p + 1e-12), (
        "p_fukusho_hit_lower <= p_fukusho_hit (D-01: max(0, p_final - q_shrink) <= p_final)"
    )
    # p_lower >= 0 (D-01・max(0, ...) の下限クリップ)
    assert np.all(p_lower >= 0.0 - 1e-12), "p_fukusho_hit_lower >= 0 (D-01 下限クリップ)"


# ---------------------------------------------------------------------------
# Test 4: byte-reproducible (theta=1.0 で2回 train_and_predict で p_lower が bit-identical)
# ---------------------------------------------------------------------------
def test_p_lower_byte_reproducible():
    """theta=1.0 で2回 train_and_predict を呼び・p_fukusho_hit_lower 列が np.array_equal で一致
    (FIXED_REPRODUCE_TS・固定 seed/thread・SC#3 idiom・§19.1)."""
    result1 = _run_train_and_predict_minimal(score_split="calib")
    result2 = _run_train_and_predict_minimal(score_split="calib")
    p_lower_1 = result1["pred_df"]["p_fukusho_hit_lower"].to_numpy()
    p_lower_2 = result2["pred_df"]["p_fukusho_hit_lower"].to_numpy()
    assert np.array_equal(p_lower_1, p_lower_2), (
        "p_fukusho_hit_lower が2回呼出で bit-identical (§19.1・SC#3・byte-reproducible)"
    )
    # q_shrink も同一 (決定論的)
    assert result1["p_lower_q_shrink"] == result2["p_lower_q_shrink"]


# ---------------------------------------------------------------------------
# Test 5: return dict provenance (p_lower_q_level/q_shrink/shrinkage_method)
# ---------------------------------------------------------------------------
def test_return_dict_p_lower_provenance():
    """return dict に p_lower_q_level=0.90・p_lower_q_shrink=float・
    p_lower_shrinkage_method='calibration_residual_conformal' が含まれる (§19.1 再現性)."""
    result = _run_train_and_predict_minimal(score_split="calib")
    assert result["p_lower_q_level"] == 0.90, "p_lower_q_level=0.90 (D-02 事前登録値)"
    assert isinstance(result["p_lower_q_shrink"], float), "p_lower_q_shrink は float (D-02)"
    assert result["p_lower_shrinkage_method"] == "calibration_residual_conformal", (
        "p_lower_shrinkage_method='calibration_residual_conformal' (D-01)"
    )


# ---------------------------------------------------------------------------
# Test 6: artifact metadata (save_native_artifact で3キーが記録される)
# ---------------------------------------------------------------------------
def test_save_native_artifact_p_lower_metadata(tmp_path):
    """save_native_artifact で metadata.json に p_lower_q_level/p_lower_q_shrink/
    p_lower_shrinkage_method が記録される (race_relative_theta idiom と同一・§19.1)."""
    feature_df = _build_label_joined_feature_df_with_entry_count(
        n_train_races=60, n_calib_races=24, n_test_races=24, n_holdout_races=12
    )
    result = _run_train_and_predict_minimal(score_split="calib")
    out_dir = tmp_path / "artifact_test"
    save_native_artifact(
        result["calibrated"],
        base_model_type="lightgbm",
        model_version=result["model_version"],
        feature_snapshot_id="20260627-1a-test",
        hyperparams={"seed": 42},
        seed=42,
        train_calib_test_periods={"train": "2016-2023", "calib": "2024H1", "test": "2024H2"},
        calib_method=result["calib_method"],
        race_relative_theta=1.0,
        p_lower_q_level=result["p_lower_q_level"],
        p_lower_q_shrink=result["p_lower_q_shrink"],
        p_lower_shrinkage_method=result["p_lower_shrinkage_method"],
        out_dir=out_dir,
    )
    metadata_path = out_dir / "metadata.json"
    assert metadata_path.exists()
    with metadata_path.open(encoding="utf-8") as f:
        meta = json.load(f)
    assert "p_lower_q_level" in meta
    assert "p_lower_q_shrink" in meta
    assert "p_lower_shrinkage_method" in meta
    assert meta["p_lower_q_level"] == 0.90
    assert meta["p_lower_shrinkage_method"] == "calibration_residual_conformal"


# ---------------------------------------------------------------------------
# Test 7: silent fallback 禁止 (pred_proba_lower と pred_proba の index/長さ不整合で RuntimeError)
# ---------------------------------------------------------------------------
def test_predict_p_fukusho_pred_proba_lower_index_mismatch_fail_loud():
    """[Shared Pattern 4] predict_p_fukusho で pred_proba_lower と X の index/長さが不整合の場合・
    RuntimeError で fail-loud (silent wrong-horse p_lower 防止・Cycle 2 NEW HIGH-1 鏡像)."""
    # 最小の synthetic X と race_df を構築して・pred_proba_lower だけ index をずらす.
    rng = np.random.default_rng(42)
    n = 6
    idx = pd.RangeIndex(0, n)
    X = pd.DataFrame({"feat_a": rng.normal(size=n)}, index=idx)
    race_df = pd.DataFrame(index=idx)
    for col in ["year", "jyocd", "kaiji", "nichiji", "racenum", "umaban", "kettonum"]:
        race_df[col] = 1
    race_df["race_date"] = pd.Timestamp("2024-07-01")

    # ダミーの calibrated estimator (predict_proba を持つ)
    class _DummyEst:
        def predict_proba(self, X):
            p = np.clip(rng.random(len(X)), 0.01, 0.99)
            return np.column_stack([1 - p, p])

    pred_proba = pd.Series(rng.random(n), index=idx)
    # index をずらした pred_proba_lower (silent wrong-horse p_lower になる・これを弾く)
    wrong_idx = pd.RangeIndex(100, 100 + n)
    pred_proba_lower = pd.Series(rng.random(n), index=wrong_idx)
    with pytest.raises(RuntimeError, match=r"pred_proba_lower"):
        predict_p_fukusho(
            _DummyEst(),
            X,
            model_type="lightgbm_rr",
            model_version="test-v1",
            feature_snapshot_id="test",
            calib_method="isotonic",
            race_df=race_df,
            split_label="test",
            pred_proba=pred_proba,
            pred_proba_lower=pred_proba_lower,  # index 不整合
        )


# ---------------------------------------------------------------------------
# Test 10: [C-12-02-1 / HIGH] q_shrink 外部注入で p_lower 生成 (score_split='test')
# ---------------------------------------------------------------------------
def test_q_shrink_external_injection_yields_p_lower_on_test():
    """[C-12-02-1 HIGH] score_split='test'・theta=1.0・p_lower_q_shrink=<calibで計算した値> の呼出で
    pred_df['p_fukusho_hit_lower'] が非 NULL かつ p_lower <= p_fukusho_hit
    (外部注入 q_shrink を test 窓 p_final に適用・§11.2 聖域・test 窓 outcome を使わない)."""
    # 1) score_split='calib' で一度呼んで・q_shrink を計算 (calib slice のみ・§11.2 聖域)
    calib_result = _run_train_and_predict_minimal(score_split="calib")
    q_shrink_from_calib = calib_result["p_lower_q_shrink"]
    assert q_shrink_from_calib is not None and q_shrink_from_calib > 0.0

    # 2) score_split='test' で外部注入して p_lower を test 窓 p_final に適用
    test_result = _run_train_and_predict_minimal(
        score_split="test",
        p_lower_q_shrink=q_shrink_from_calib,  # 外部注入 (calib slice で計算済み)
    )
    pred_df = test_result["pred_df"]
    p = pred_df["p_fukusho_hit"].to_numpy(dtype=float)
    p_lower = pred_df["p_fukusho_hit_lower"].to_numpy(dtype=float)
    # 非 NULL
    assert np.all(np.isfinite(p_lower)), (
        "score_split='test' + 外部注入 q_shrink で p_fukusho_hit_lower が非 NULL (C-12-02-1 HIGH)"
    )
    # p_lower <= p_fukusho_hit (D-01: max(0, p_final - q_shrink) <= p_final)
    assert np.all(p_lower <= p + 1e-12), "p_lower <= p_fukusho_hit (D-01)"
    # provenance: 外部注入値がそのまま記録される
    assert test_result["p_lower_q_shrink"] == q_shrink_from_calib
    assert test_result["p_lower_q_level"] == 0.90
    assert test_result["p_lower_shrinkage_method"] == "calibration_residual_conformal"
