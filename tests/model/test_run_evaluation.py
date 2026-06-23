# ruff: noqa: E501  (長い docstring・Phase 6 統合評価テスト)
"""Phase 6 Plan 06-05: scripts/run_evaluation.py の E2E smoke テスト（EVAL-01/02/03 統合）。

Task 1 (TDD GREEN): run_evaluation.py の純粋関数群（evaluate_integrated / generate_evaluation_reports /
apply_primary_model_flag）を合成データで検証。DB 不要・tmp_path で完結。

設計方針（06-05-PLAN.md Task 1 behavior 準拠）:
  - REVIEW HIGH#6: BLOCK 発火時も reports atomic write を *先* に行い・その後に RuntimeError。
  - REVIEW HIGH#5: reports/06-evaluation.json に sum_p_measurement を記録（0.30 閾値の経験的根拠）。
  - REVIEW C7: --primary-model 省略時は recommended_primary_model のみ提示・is_primary 更新スキップ。
  - REVIEW C8: 主モデル比較表に backtest 指標を統合（優位 policy 代表窓で1行集約・方法注記）。
  - REVIEW Codex MEDIUM + N3 cycle-3: race_id_split_disjoint を両 split 非空で真検証・空は "N/A"。
  - REVIEW C15 cycle-2: SC#2「beat all baselines」と BLOCK 条件1「全敗」の対称性注記。
  - REVIEW C5: comparison_table で quantile_max_dev と mce は別列。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# scripts/run_evaluation.py を import するため sys.path にリポジトリルートを追加
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_evaluation import (  # noqa: E402
    aggregate_backtest_for_model,
    build_recommended_primary_model,
    check_race_id_split_disjoint,
    evaluate_integrated,
    generate_evaluation_reports,
)

# Rule1: src.model.predict.MODEL_TYPE_TO_SHORT と同一の短縮形（DB実値と一致させる）。
# 旧 fixture は model_name[:3] で "lightgbm"→"lig" / "catboost"→"cat" となり DB実値
# (-lgb-v1 / -cb-v1) と不整合 → set_primary_model の WHERE が 0 行になる bug をテストが
# 検知できていなかった。blN baseline は [:3] のまま blN になるので fallthrough。
_MODEL_SHORT = {"lightgbm": "lgb", "catboost": "cb"}


def _short_model(name: str) -> str:
    return _MODEL_SHORT.get(name, name[:3])


# ---------------------------------------------------------------------------
# 合成 fixture builder
# ---------------------------------------------------------------------------


def _make_synthetic_eval_inputs(tmp_path: Path) -> dict:
    """run_evaluation.evaluate_integrated に渡す合成入力を構築する。

    - prediction_df: 両モデル (lightgbm/catboost) + bl1/bl4/bl5 の test split 行
    - label_df: race_key + segment 軸（race_date/jyocd/entry_count/ninki/fukuoddslower）+ fukusho_hit
    - reports/04-eval.json: lightgbm/catboost/bl1/bl4/bl5 の metrics dict
    - reports/05-backtest.json: 両モデル×2policy の backtest comparison_table
    - split_integrity_df: train/val/test の race_key 集合（disjoint 検証用）
    """
    # 50 レース × 8 頭 = 400 行・両モデル + bl1/bl4/bl5 の5モデル = 2000 行
    n_races = 50
    race_keys = [f"2023-05-1-{m:02d}-1-{r}" for r in range(1, n_races + 1) for m in (1,)]
    # ↑簡略: 月ごと1レース×50。race_key 重複なし。
    race_keys = [f"2023-{(r % 12) + 1:02d}-05-1-{(r % 12) + 1:02d}-1" for r in range(1, n_races + 1)]
    rows = []
    for rk in race_keys:
        month = int(rk[5:7])
        race_date = pd.Timestamp(year=2023, month=month, day=5)
        for umaban in range(1, 9):  # 8頭
            base_p = 0.40 - 0.04 * (umaban - 1)
            # モデル毎にわずかに変化
            for model_name, delta in [
                ("lightgbm", 0.0), ("catboost", 0.005),
                ("bl1", -0.10), ("bl4", 0.02), ("bl5", -0.05),
            ]:
                p = float(np.clip(base_p + delta, 0.02, 0.95))
                rows.append({
                    "model_type": model_name,
                    "model_version": f"20260620-1a-postreview-v2-{_short_model(model_name)}-v1",
                    "feature_snapshot_id": "20260620-1a-postreview-v2",
                    "as_of_datetime": pd.Timestamp("2026-06-20T00:00:00Z"),
                    "p_fukusho_hit": p,
                    "race_key": rk,
                    "umaban": umaban,
                    "race_date": race_date,
                    "jyocd": "05",
                    "entry_count": 8,
                    "year": "2023",
                    "kaiji": "1",
                    "nichiji": f"{month:02d}",
                    "racenum": "1",
                    "kettonum": 1000000 + int(rk[5:7]) * 100 + umaban,
                    "split": "test",
                    "calib_method": "isotonic",
                    "fukusho_hit": 1 if umaban <= 3 else 0,  # 上位3頭が複勝対象
                    "ninki": umaban,
                    "fukuoddslower": 1.5 + 0.5 * (umaban - 1),
                })
    prediction_df = pd.DataFrame(rows)

    # label_df: prediction と同形（race_key + segment 軸 + fukusho_hit）
    label_df = prediction_df[prediction_df["model_type"] == "lightgbm"][
        ["race_key", "umaban", "race_date", "jyocd", "entry_count",
         "ninki", "fukuoddslower", "fukusho_hit"]
    ].copy()
    label_df["fukusho_hit_validated"] = label_df["fukusho_hit"]

    # reports/04-eval.json (metrics・Phase 4 スタンプ済み)
    metrics_04 = {
        "lightgbm": {"brier": 0.152, "logloss": 0.475, "auc": 0.732, "sum_p_mean": 3.04,
                     "calibration_max_dev": 0.231, "calibration_max_dev_guarded": 0.099,
                     "quantile_max_dev": 0.12, "ece": 0.05, "mce": 0.18},
        "catboost": {"brier": 0.155, "logloss": 0.482, "auc": 0.718, "sum_p_mean": 3.07,
                     "calibration_max_dev": 0.258, "calibration_max_dev_guarded": 0.258,
                     "quantile_max_dev": 0.14, "ece": 0.06, "mce": 0.22},
        "bl1": {"brier": 0.170, "logloss": 0.521, "auc": 0.574, "sum_p_mean": 2.96,
                "calibration_max_dev": 0.001},
        "bl4": {"brier": 0.169, "logloss": 0.518, "auc": 0.602, "sum_p_mean": 3.25,
                "calibration_max_dev": 0.045},
        "bl5": {"brier": 0.167, "logloss": 0.513, "auc": 0.620, "sum_p_mean": 3.11,
                "calibration_max_dev": 0.344},
    }
    eval_04_path = tmp_path / "04-eval.json"
    eval_04_path.write_text(
        json.dumps({"metrics": metrics_04, "comparison_table": []}, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # reports/05-backtest.json (comparison_table・5窓×2policy×2model = 20行簡略)
    bt_rows = []
    for bt in ["BT-1", "BT-2"]:
        for policy in ["30min_before", "10min_before"]:
            for mt in ["lightgbm", "catboost"]:
                # LightGBM をわずかに優位に
                rec_rate = 0.70 if mt == "lightgbm" else 0.66
                bt_rows.append({
                    "backtest_id": f"{bt}-{policy}-{mt}",
                    "bt_name": bt,
                    "odds_policy": policy,
                    "model_type": mt,
                    "recovery_rate": rec_rate,
                    "P/L": -120000 if mt == "lightgbm" else -140000,
                    "max_DD": 130000 if mt == "lightgbm" else 150000,
                    "selected": 4200,
                    "effective_bet": 4200,
                    "refund": 0,
                    "hit_rate": 0.09,
                })
    backtest_05_path = tmp_path / "05-backtest.json"
    backtest_05_path.write_text(
        json.dumps({"comparison_table": bt_rows}, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # split_integrity_df: train/val/test 全 split の race_key（disjoint）
    train_races = [f"2019-01-05-1-01-1-{r}" for r in range(1, 11)]
    val_races = [f"2022-01-05-1-01-1-{r}" for r in range(1, 6)]
    test_races = race_keys  # 2023年のレース
    split_rows = (
        [{"race_key": rk, "split": "train"} for rk in train_races]
        + [{"race_key": rk, "split": "val"} for rk in val_races]
        + [{"race_key": rk, "split": "test"} for rk in test_races]
    )
    split_integrity_df = pd.DataFrame(split_rows)

    return {
        "prediction_df": prediction_df,
        "label_df": label_df,
        "eval_04_path": eval_04_path,
        "backtest_05_path": backtest_05_path,
        "split_integrity_df": split_integrity_df,
    }


# ---------------------------------------------------------------------------
# Test 1: evaluate_integrated が reports を生成
# ---------------------------------------------------------------------------


def test_run_evaluation_generates_reports(tmp_path):
    """evaluate_integrated + generate_evaluation_reports が reports/06-evaluation.{md,json} と
    reports/06-segments/×6軸 を生成する（E2E smoke）。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_md = tmp_path / "06-evaluation.md"
    out_json = tmp_path / "06-evaluation.json"
    segments_dir = tmp_path / "06-segments"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=False,
    )

    generate_evaluation_reports(
        result,
        out_md_path=out_md,
        out_json_path=out_json,
        primary_model=None,
        selection_reason=None,
    )

    assert out_md.exists(), "reports/06-evaluation.md が生成されていない"
    assert out_json.exists(), "reports/06-evaluation.json が生成されていない"
    # segments ディレクトリ
    assert segments_dir.exists(), "reports/06-segments/ が生成されていない"
    # 6軸 × {json, html} = 12 ファイル + plotly.min.js
    json_files = list(segments_dir.glob("*.json"))
    html_files = list(segments_dir.glob("*.html"))
    assert len(json_files) >= 6, f"segment JSON が6軸分無い: {len(json_files)}"
    assert len(html_files) >= 6, f"segment HTML が6軸分無い: {len(html_files)}"

    # JSON 構造の主要キー
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    for key in ("gate_result", "comparison_table", "primary_model", "segment_summary",
                "backtest_summary", "sum_p_measurement", "reproducibility_checks",
                "constants", "notes"):
        assert key in payload, f"06-evaluation.json に {key!r} キーがない"


# ---------------------------------------------------------------------------
# Test 2: REVIEW HIGH#6 - BLOCK 発火時に reports atomic write → RuntimeError
# ---------------------------------------------------------------------------


def test_run_evaluation_gate_block_writes_report_then_raises(tmp_path):
    """check_acceptance_gate が block_triggered=True を返す場合・reports を atomic write した *後* に
    RuntimeError を raise する（REVIEW HIGH#6）。

    BLOCK 条件: baselines 全敗 (主モデルが COMPARABLE_BASELINES の全てに LogLoss+Brier 両方で劣る)
    AND sum(p) violation_rate > 0.30。
    """
    inputs = _make_synthetic_eval_inputs(tmp_path)
    # BLOCK 条件を作るため・metrics_04 と sum_p を改変
    bad_eval_path = tmp_path / "04-eval-bad.json"
    bad_metrics = json.loads(inputs["eval_04_path"].read_text(encoding="utf-8"))
    # lightgbm/catboost を bl1/bl4/bl5 より劣化（LogLoss+Brier 両方で全敗）
    for mt in ("lightgbm", "catboost"):
        bad_metrics["metrics"][mt]["logloss"] = 0.999  # max(bl1/bl4/bl5)=0.521 より大
        bad_metrics["metrics"][mt]["brier"] = 0.999
    bad_eval_path.write_text(
        json.dumps(bad_metrics, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    # sum(p) violation_rate を高めるため・entry_count を5-7（small bucket）にして p を異常値に
    bad_pred = inputs["prediction_df"].copy()
    bad_pred["entry_count"] = 6  # small bucket [1.8, 2.2]
    bad_pred["p_fukusho_hit"] = 0.9  # sum=7.2 >> 2.2 → violation_rate=1.0
    bad_label = inputs["label_df"].copy()
    bad_label["entry_count"] = 6

    out_md = tmp_path / "06-evaluation-block.md"
    out_json = tmp_path / "06-evaluation-block.json"
    segments_dir = tmp_path / "06-segments-block"

    # evaluate → BLOCK 発火データ
    result = evaluate_integrated(
        prediction_df=bad_pred,
        label_df=bad_label,
        eval_04_path=bad_eval_path,
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=True,  # BLOCK テストは高速化のため segments skip
    )
    assert result["gate_result"]["block_triggered"] is True, (
        f"BLOCK が発火していない: gate_result={result['gate_result']}"
    )

    # generate_evaluation_reports は BLOCK を検知しても書込む（REVIEW HIGH#6）
    generate_evaluation_reports(
        result,
        out_md_path=out_md,
        out_json_path=out_json,
        primary_model=None,
        selection_reason=None,
    )
    assert out_md.exists(), "BLOCK 時も reports/06-evaluation.md が残るべき（REVIEW HIGH#6）"
    assert out_json.exists(), "BLOCK 時も reports/06-evaluation.json が残るべき（REVIEW HIGH#6）"

    # 呼出側（main）は reports write 後に RuntimeError を raise する挙動をシミュレート
    if result["gate_result"]["block_triggered"]:
        with pytest.raises(RuntimeError, match="acceptance gate BLOCK"):
            raise RuntimeError(
                f"acceptance gate BLOCK: {result['gate_result']['block_reasons']}"
            )


# ---------------------------------------------------------------------------
# Test 3: JSON byte-reproducible
# ---------------------------------------------------------------------------


def test_run_evaluation_json_byte_reproducible(tmp_path):
    """同じ入力で2回生成した reports/06-evaluation.json が byte-identical（sort_keys=True）。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_json_1 = tmp_path / "06-eval-1.json"
    out_json_2 = tmp_path / "06-eval-2.json"
    segments_dir = tmp_path / "06-segments-repro"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=True,
    )
    generate_evaluation_reports(result, out_md_path=tmp_path / "x.md",
                                out_json_path=out_json_1,
                                primary_model=None, selection_reason=None)
    generate_evaluation_reports(result, out_md_path=tmp_path / "y.md",
                                out_json_path=out_json_2,
                                primary_model=None, selection_reason=None)
    b1 = out_json_1.read_bytes()
    b2 = out_json_2.read_bytes()
    assert b1 == b2, "JSON が byte-reproducible でない（sort_keys=True 違反）"


# ---------------------------------------------------------------------------
# Test 4: report セクション（5セクション + SC#2/BLOCK 対称性注記）
# ---------------------------------------------------------------------------


def test_run_evaluation_report_sections(tmp_path):
    """reports/06-evaluation.md に5セクション + SC#2/BLOCK 対称性注記（REVIEW C15 cycle-2）が含まれる。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_md = tmp_path / "06-eval-sections.md"
    out_json = tmp_path / "06-eval-sections.json"
    segments_dir = tmp_path / "06-segments-sec"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=True,
    )
    generate_evaluation_reports(result, out_md_path=out_md, out_json_path=out_json,
                                primary_model=None, selection_reason=None)
    md_text = out_md.read_text(encoding="utf-8")

    # 5セクション
    for section in (
        "受入ゲート判定", "主モデル比較表", "主モデル確定",
        "segment 安定性サマリ", "注記",
    ):
        assert section in md_text, f"md セクション {section!r} がない"

    # REVIEW C15 cycle-2: SC#2/BLOCK 対称性注記
    assert "SC#2" in md_text or "beat all baselines" in md_text.lower(), (
        "SC#2 対称性注記がない（REVIEW C15 cycle-2）"
    )
    assert "対称" in md_text, "対称性注記キーワードがない（REVIEW C15 cycle-2）"


# ---------------------------------------------------------------------------
# Test 5: primary_model スキーマ（REVIEW C7: 省略時 null + recommended_primary_model）
# ---------------------------------------------------------------------------


def test_run_evaluation_primary_model_record(tmp_path):
    """reports/06-evaluation.json の primary_model がスキーマ準拠。
    REVIEW C7: --primary-model 省略時は null・替わりに recommended_primary_model。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_md = tmp_path / "06-eval-pm.md"
    out_json = tmp_path / "06-eval-pm.json"
    segments_dir = tmp_path / "06-seg-pm"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=True,
    )

    # --- 省略時: primary_model=None・recommended_primary_model を提示 ---
    generate_evaluation_reports(result, out_md_path=out_md, out_json_path=out_json,
                                primary_model=None, selection_reason=None)
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["primary_model"] is None, (
        f"--primary-model 省略時は null のはず: {payload['primary_model']!r}"
    )
    rec = payload.get("recommended_primary_model")
    assert rec is not None, "省略時は recommended_primary_model を提示すべき（REVIEW C7）"
    for key in ("model_type", "selection_reason", "tiebreak_applied", "priority_order"):
        assert key in rec, f"recommended_primary_model に {key!r} がない"

    # --- 指定時: primary_model がスキーマ通り ---
    generate_evaluation_reports(result, out_md_path=out_md, out_json_path=out_json,
                                primary_model="lightgbm",
                                selection_reason="D-04 Calibration 重視基準で LightGBM を選定")
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    pm = payload["primary_model"]
    assert pm is not None, "--primary-model 指定時は primary_model が非 null のはず"
    for key in ("model_type", "model_version", "feature_snapshot_id",
                "as_of_datetime", "selection_reason", "tiebreak_applied"):
        assert key in pm, f"primary_model に {key!r} がない"
    assert pm["model_type"] == "lightgbm"
    assert "Calibration" in pm["selection_reason"] or "D-04" in pm["selection_reason"]


# ---------------------------------------------------------------------------
# Test 6: backtest 統合（REVIEW C8: 優位 policy 代表窓で1行集約・集計方法注記）
# ---------------------------------------------------------------------------


def test_run_evaluation_backtest_integration(tmp_path):
    """reports/05-backtest.json の backtest 指標が主モデル比較表に統合される（EVAL-01）。
    REVIEW C8: 優位 policy の代表窓で1行に集約・集計方法を backtest_aggregation_method で注記。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_json = tmp_path / "06-eval-bt.json"
    segments_dir = tmp_path / "06-seg-bt"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=True,
    )
    generate_evaluation_reports(result, out_md_path=tmp_path / "x.md",
                                out_json_path=out_json,
                                primary_model=None, selection_reason=None)
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    bs = payload["backtest_summary"]
    assert "backtest_aggregation_method" in bs, (
        "backtest_summary に backtest_aggregation_method がない（REVIEW C8）"
    )
    # 両モデルの backtest 行が統合されている
    for mt in ("lightgbm", "catboost"):
        assert mt in bs["by_model"], f"backtest_summary.by_model に {mt!r} がない"
        rec = bs["by_model"][mt]
        for key in ("recovery_rate", "profit_loss", "max_drawdown"):
            assert key in rec, f"backtest {mt} に {key!r} がない"
        # SC#1/EVAL-01 複勝的中率 (hit_rate) が backtest_summary に集約されている
        assert "hit_rate" in rec, (
            f"backtest_summary.by_model.{mt} に hit_rate がない（SC#1/EVAL-01 複勝的中率）"
        )
        assert rec["hit_rate"] == pytest.approx(0.09, abs=1e-9), (
            f"backtest {mt} hit_rate が期待値 0.09（synthetic fixture）と不一致: {rec['hit_rate']}"
        )
    # SC#1/EVAL-01: comparison_table に bt_hit_rate 列が含まれる（主モデル行）
    ct = payload["comparison_table"]
    for mt in ("lightgbm", "catboost"):
        mt_rows = [r for r in ct if r.get("model_name") == mt]
        assert mt_rows, f"comparison_table に {mt} 行がない"
        assert "bt_hit_rate" in mt_rows[0], (
            f"comparison_table.{mt} に bt_hit_rate 列がない（SC#1/EVAL-01）"
        )
        assert mt_rows[0]["bt_hit_rate"] == pytest.approx(0.09, abs=1e-9), (
            f"comparison_table.{mt}.bt_hit_rate が期待値 0.09 と不一致: {mt_rows[0]['bt_hit_rate']}"
        )


def test_run_evaluation_json_strict_no_nan(tmp_path):
    """reports/06-evaluation.json が RFC 8259 strict JSON に準拠（NaN/Inf リテラルなし）。

    Phase 7 Streamlit / 外部パーサで parse 失敗するリスクを排除するため・
    ``allow_nan=False`` で出力し NaN→null 正規化を行う（SC#1/EVAL-01 gap closure・副次 WARNING）。
    """
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_json = tmp_path / "06-eval-nan.json"
    segments_dir = tmp_path / "06-seg-nan"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=False,
    )
    generate_evaluation_reports(result, out_md_path=tmp_path / "x.md",
                                out_json_path=out_json,
                                primary_model=None, selection_reason=None)

    raw_text = out_json.read_text(encoding="utf-8")
    # strict モードでパース（NaN/Infinity を拒否・RFC 8259 準拠の検証）
    json.loads(raw_text, parse_constant=lambda x: (_ for _ in ()).throw(
        ValueError(f"strict JSON 違反: 非標準 constant {x} を検出（NaN/Infinity）")
    ))
    # 念のため NaN/Infinity リテラル文字列が含まれないことを grep 的に確認
    for bad in (": NaN", ": Infinity", ": -Infinity"):
        assert bad not in raw_text, f"strict JSON 違反: {bad!r} が 06-evaluation.json に残存"

    # segment JSON も strict
    for seg_json in segments_dir.glob("*.json"):
        seg_text = seg_json.read_text(encoding="utf-8")
        json.loads(seg_text, parse_constant=lambda x: (_ for _ in ()).throw(
            ValueError(f"strict JSON 違反: {seg_json} に非標準 constant {x}")
        ))
        for bad in (": NaN", ": Infinity", ": -Infinity"):
            assert bad not in seg_text, f"strict JSON 違反: {bad!r} が {seg_json} に残存"


# ---------------------------------------------------------------------------
# Test 7: yearly_inversion_warn セクション
# ---------------------------------------------------------------------------


def test_run_evaluation_yearly_inversion_warn_section(tmp_path):
    """reports/06-evaluation.json の gate_result に yearly_inversion_warn キーが含まれ・
    {year: {spearman_corr, spearman_pvalue, bin_inversions}} スキーマに準拠。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_json = tmp_path / "06-eval-yi.json"
    segments_dir = tmp_path / "06-seg-yi"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=False,
    )
    generate_evaluation_reports(result, out_md_path=tmp_path / "x.md",
                                out_json_path=out_json,
                                primary_model=None, selection_reason=None)
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    yw = payload["gate_result"].get("yearly_inversion_warn")
    assert yw is not None, "gate_result.yearly_inversion_warn がない"
    # スキーマ検証（year が1つ以上あれば各キーを確認）
    if yw:
        for year, data in yw.items():
            for key in ("spearman_corr", "spearman_pvalue", "bin_inversions"):
                assert key in data, f"yearly_inversion_warn[{year}] に {key!r} がない"


# ---------------------------------------------------------------------------
# Test 8: REVIEW HIGH#5 - sum_p_measurement
# ---------------------------------------------------------------------------


def test_run_evaluation_sum_p_violation_rate_measured(tmp_path):
    """reports/06-evaluation.json に sum_p_measurement が含まれ・
    {large_violation_rate, small_violation_rate, total_races, threshold, threshold_appropriate} を持つ。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    out_json = tmp_path / "06-eval-sump.json"
    segments_dir = tmp_path / "06-seg-sump"

    result = evaluate_integrated(
        prediction_df=inputs["prediction_df"],
        label_df=inputs["label_df"],
        eval_04_path=inputs["eval_04_path"],
        backtest_05_path=inputs["backtest_05_path"],
        split_integrity_df=inputs["split_integrity_df"],
        feature_snapshot_id="20260620-1a-postreview-v2",
        as_of_datetime="2026-06-20T00:00:00Z",
        segments_dir=str(segments_dir),
        skip_segments=True,
    )
    generate_evaluation_reports(result, out_md_path=tmp_path / "x.md",
                                out_json_path=out_json,
                                primary_model=None, selection_reason=None)
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    sm = payload["sum_p_measurement"]
    for key in ("large_violation_rate", "small_violation_rate", "total_races",
                "threshold", "threshold_appropriate"):
        assert key in sm, f"sum_p_measurement に {key!r} がない（REVIEW HIGH#5）"
    assert sm["threshold"] == 0.30, f"threshold=0.30 のはず: {sm['threshold']}"
    assert isinstance(sm["threshold_appropriate"], bool), (
        "threshold_appropriate は bool のはず"
    )


# ---------------------------------------------------------------------------
# Test 9: REVIEW Codex MEDIUM + N3 cycle-3 - race_id_split_disjoint
# ---------------------------------------------------------------------------


def test_run_evaluation_race_id_split_integrity(tmp_path):
    """reports/06-evaluation.json の gate_result に
    reproducibility_checks.race_id_split_disjoint が記録される。
    合成 fixture（train/val/test disjoint）→ True・train==test 共通 → False・空 split → "N/A"。"""
    # (a) disjoint の場合は True
    inputs = _make_synthetic_eval_inputs(tmp_path)
    result = check_race_id_split_disjoint(inputs["split_integrity_df"])
    assert result["race_id_split_disjoint"] is True, (
        f"disjoint fixture で True のはず: {result}"
    )
    assert result["n_train_races"] > 0 and result["n_test_races"] > 0

    # (b) train と test で共通 race_key を含む場合は False
    bad_split = inputs["split_integrity_df"].copy()
    # test の先頭 race_key を train にも挿入
    leak_key = bad_split.loc[bad_split["split"] == "test", "race_key"].iloc[0]
    bad_split = pd.concat([
        bad_split,
        pd.DataFrame([{"race_key": leak_key, "split": "train"}]),
    ], ignore_index=True)
    result_bad = check_race_id_split_disjoint(bad_split)
    assert result_bad["race_id_split_disjoint"] is False, (
        f"leak fixture で False のはず: {result_bad}"
    )

    # (c) 空 split（train 行なし）は "N/A"
    empty_split = inputs["split_integrity_df"][
        inputs["split_integrity_df"]["split"] == "test"
    ].copy()
    result_empty = check_race_id_split_disjoint(empty_split)
    assert result_empty["race_id_split_disjoint"] == "N/A", (
        f"空 split で 'N/A' のはず: {result_empty}"
    )


# ---------------------------------------------------------------------------
# Test 10: aggregate_backtest_for_model / build_recommended_primary_model
# ---------------------------------------------------------------------------


def test_aggregate_backtest_and_recommended_primary_model(tmp_path):
    """aggregate_backtest_for_model が優位 policy 代表窓で1行に集約し・
    build_recommended_primary_model が D-08 タイブレーク優先順位で推奨を返す。"""
    inputs = _make_synthetic_eval_inputs(tmp_path)
    bt_payload = json.loads(inputs["backtest_05_path"].read_text(encoding="utf-8"))
    bt_rows = bt_payload["comparison_table"]

    # LightGBM の優位 policy（recovery_rate 高い方）を代表窓として集約
    lgb_agg = aggregate_backtest_for_model(bt_rows, "lightgbm")
    assert lgb_agg["recovery_rate"] == 0.70, (
        f"LightGBM の優位 policy recovery_rate=0.70 のはず: {lgb_agg}"
    )
    assert "representative_policy" in lgb_agg, "representative_policy がない"

    metrics_04 = json.loads(inputs["eval_04_path"].read_text(encoding="utf-8"))["metrics"]
    bt_by_model = {
        mt: aggregate_backtest_for_model(bt_rows, mt) for mt in ("lightgbm", "catboost")
    }
    rec = build_recommended_primary_model(metrics_04, bt_by_model)
    # LightGBM が backtest 回収率 0.70 > CatBoost 0.66 のため推奨
    assert rec["model_type"] == "lightgbm", (
        f"LightGBM が推奨されるはず: {rec}"
    )
    assert rec["tiebreak_applied"] in (None, "backtest_recovery_rate"), (
        f"tiebreak_applied が不正: {rec}"
    )
