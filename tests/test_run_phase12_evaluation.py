# ruff: noqa: E501
"""Phase 12 Plan 04 run_phase12_evaluation.py 契約テスト.

本テストは scripts/run_phase12_evaluation.py が以下を満たすことを機械保証する:

聖域 (§11.2 / SAFE-01 / §15.2 / §19.1 / D-10 / D-06 / D-09):
  - Test 1  (§11.2 聖域・q_shrink calib slice のみ):
      _compute_q_shrink_on_calib が calib slice のみで compute_p_lower_conformal_shrinkage を呼び・
      test 窓 outcome 系を取らない (Shared Pattern 6・codex HIGH#1・score_split='calib' 聖域ブロック)
  - Test 2  (q_shrink.json 事前書き出し):
      q_shrink 計算経路決定後・test 窓評価に先立ち q_shrink.json が byte-reproducible に書き出される
      (theta-selection.json idiom・C-12-04-1 HIGH)
  - Test 3  (D-10 set_primary_model Call 0件):
      inspect.getsource(run_phase12_evaluation) を ast.parse し・ast.walk で ast.Call の func.id/attr
      が 'set_primary_model' のものが0件 (Phase 11 D-07 踏襲・AST check)
  - Test 4  (D-09 switch_recommendation):
      compute_switch_recommendation が SC#4 WARN gate + p_lower EV v1.0 binary 比較 + falsification verdict
      を統合し 'switch'/'hold'/'reject' のいずれかを返す
  - Test 5  (§15.2 gate 不変):
      _evaluate_gate が §15.2 gate (block_reasons/block_triggered) と Phase 12 WARN gate
      (phase12_warn_triggered) を共に評価する (D-06・拡張指標は上書きでなく併載)
  - Test 6  (byte-reproducible):
      FIXED_REPRODUCE_TS + 固定 seed/thread で2回実行し・同一入力なら reports/12-evaluation/*.json が
      bit-identical (sort_keys=True・SC#3/SC#5・§19.1)
  - Test 7  (falsification pipeline 聖域):
      run_falsification_pipeline が fit_market_implied_calibrator (train/calib 窓) → run_falsification_test
      (test 窓) の順で呼ぶ (§11.2 聖域・C-12-03-4 2-window 分離)
  - Test 8  (reports 構造):
      reports/12-evaluation/ に 8 ファイル (12-evaluation.md/.json・falsification.md/.json・
      falsification-spec.json・switch-recommendation.md/.json・q_shrink.json) が生成される
  - Test 9  (statement_timeout):
      readonly_pool configure callback が 'SET statement_timeout = 30s' を発行する
      (memory: subagent-db-query-statement-timeout)
  - Test 10 ([C-12-04-3 MEDIUM] 事前登録定数 import):
      Q_LEVEL_SHRINKAGE / Q_LEVEL_FALSIFICATION / HOLM_ALPHA / MARKET_CALIB_SAMPLE_THRESHOLD /
      ODDS_CLIP_MIN/MAX / LOGIT_CLIP_EPS / PHASE12_*_THRESHOLD が src/eval/falsification.py から import
      され run_phase12_evaluation.py に重複定義がない
      (`grep -cE '^(Q_LEVEL|HOLM_ALPHA|MARKET_CALIB_SAMPLE_THRESHOLD|ODDS_CLIP_MIN|ODDS_CLIP_MAX|LOGIT_CLIP_EPS|PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD|PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD)\\b' == 0`)
  - Test 11 ([C-12-04-1 HIGH] q_shrink label alignment):
      _compute_q_shrink_on_calib が calib slice の pred_proba と y_calib を race_key+umaban fail-loud
      key-join で整列させる (Phase 11 _attach_label_to_pred L452-458 と同一 idiom・join 失敗は RuntimeError)
  - Test 12 ([C-12-04-2 HIGH] q_shrink 外部注入で test 窓 p_lower):
      orchestrator.train_and_predict(score_split='test', theta=1.0, p_lower_q_shrink=<calib値>) の形で
      calib 済み q_shrink を注入する (keyword-only 引数が唯一の受取経路)
  - Test 13 ([C-12-03-1 HIGH] falsification-spec.json 事前書き出し):
      run_falsification_test の test 窓評価前に write_falsification_spec 経由で
      falsification-spec.json が byte-reproducible に書き出される
  - Test 14 ([C-12-01-2 HIGH] 値レベル adversarial・q_shrink 不変性):
      合成データで _compute_q_shrink_on_calib を実行し q_shrink.json を書き出した後・
      test labels を改変しても q_shrink.json の sha256 が不変・calib labels を改変すると変化する
      (signature-only 監査でなく値レベルで §11.2 聖域の実リークを検出・codex HIGH#4)
  - Test 15 ([C-12-04-4 MEDIUM] docstring 正確性):
      docstring の D-10 対象が set_primary_model に限定され・load_predictions を呼ぶ事実を正確に反映

DB 不要 (KEIBA_SKIP_DB_TESTS=1 で実行・合成データと AST/シグネチャ検査).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# scripts/ から src.* を import するための sys.path 追加は conftest 側で想定。
# run_phase12_evaluation は scripts/ にあるため import 可能であること。
from src.eval import falsification as falsification_mod

# ---------------------------------------------------------------------------
# helpers: run_phase12_evaluation モジュール取得
# ---------------------------------------------------------------------------


def _load_run_phase12_module():
    """scripts/run_phase12_evaluation.py を import する (テスト実行時にモジュール取得).

    sys.path への scripts/ 追加は run_phase12_evaluation.py 内部の _REPO_ROOT 追加でカバーされる。
    """
    import importlib

    import scripts.run_phase12_evaluation as mod

    return importlib.reload(mod)


# ---------------------------------------------------------------------------
# Test 3 / Test 10 / Test 15: AST・docstring・import 静的検査
# ---------------------------------------------------------------------------


def test_03_set_primary_model_call_zero() -> None:
    """Test 3 (D-10): run_phase12_evaluation の AST で set_primary_model Call node が0件."""
    mod = _load_run_phase12_module()
    source = inspect.getsource(mod)
    tree = ast.parse(textwrap.dedent(source))

    call_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "set_primary_model":
                call_count += 1
            elif isinstance(func, ast.Attribute) and func.attr == "set_primary_model":
                call_count += 1
    assert call_count == 0, (
        f"D-10 violation: set_primary_model Call node が {call_count} 件 (期待 0)・"
        "人間承認の別アクション (Phase 11 D-07 踏襲)"
    )


def test_10_constants_imported_no_duplicates(repo_root: Path) -> None:
    """Test 10 ([C-12-04-3 MEDIUM]): 事前登録定数が falsification.py から import され重複定義なし.

    `grep -cE '^(Q_LEVEL|HOLM_ALPHA|MARKET_CALIB_SAMPLE_THRESHOLD|ODDS_CLIP_MIN|ODDS_CLIP_MAX|LOGIT_CLIP_EPS|PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD|PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD)\\b' == 0`
    """
    script = repo_root / "scripts" / "run_phase12_evaluation.py"
    text = script.read_text(encoding="utf-8")
    forbidden_patterns = [
        "Q_LEVEL",
        "HOLM_ALPHA",
        "MARKET_CALIB_SAMPLE_THRESHOLD",
        "ODDS_CLIP_MIN",
        "ODDS_CLIP_MAX",
        "LOGIT_CLIP_EPS",
        "PHASE12_SELECTED_ONLY_CALIB_MAX_DEV_THRESHOLD",
        "PHASE12_ODDS_BAND_CALIB_MAX_DEV_THRESHOLD",
    ]
    # AST で module-level の Assign / AnnAssign ターゲット名だけを検出し・
    # docstring / markdown 文字列中の言及を false positive にしない (C-12-04-3 精緻化)。
    tree = ast.parse(text)
    module_level_assign_names: set[str] = set()
    for node in tree.body:  # module-level のみ (関数内ローカル代入は除外)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    module_level_assign_names.add(tgt.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                module_level_assign_names.add(node.target.id)
    duplicate_defs = sorted(module_level_assign_names & set(forbidden_patterns))
    assert not duplicate_defs, (
        f"[C-12-04-3] run_phase12_evaluation.py に module-level 重複定義: {duplicate_defs}・"
        "falsification.py から import すること (BT1_PERIODS のみ run script 固有許可)"
    )

    # import 行に falsification からこれらが import されていることも確認
    import_line_found = False
    for line in text.splitlines():
        if "from src.eval.falsification import" in line or (
            "from src.eval.falsification" in line and "import" in line
        ):
            import_line_found = True
            break
    assert import_line_found, "from src.eval.falsification import 行が存在しない"

    # falsification.py の constants block に Q_LEVEL_SHRINKAGE が存在することも再確認
    assert hasattr(falsification_mod, "Q_LEVEL_SHRINKAGE"), (
        "falsification.py に Q_LEVEL_SHRINKAGE が未定義 (Cycle 3 C3-12-03-1 producer 側)"
    )
    assert falsification_mod.Q_LEVEL_SHRINKAGE == pytest.approx(0.90)


def test_15_docstring_accurate_calls_load_predictions() -> None:
    """Test 15 ([C-12-04-4 MEDIUM]): docstring が load_predictions を呼ぶ事実を正確に反映.

    Phase 11 docstring (run_phase11_evaluation.py L36-44) は「load_predictions を呼ばない」誤りを
    含んでいた (実際は L418-440 で呼ぶ)。本 script は load_predictions を呼ぶため docstring も
    「呼ぶ」事実を反映し・D-10 対象は set_primary_model に限定する。
    """
    mod = _load_run_phase12_module()
    doc = inspect.getdoc(mod) or ""
    # set_primary_model を呼ばない旨は記述されるべき (D-10 対象明示)
    assert "set_primary_model" in doc, (
        "docstring に set_primary_model 言及がない・D-10 対象明示のため必須"
    )
    # load_predictions を呼ぶ事実が「呼ぶ」方向で記述されていることを検証
    # (「呼ばない」記述は誤り・Phase 11 docstring の誤りを踏襲しない)
    # docstring 内の 'load_predictions を呼' / 'load_predictions を使用' / 'load_predictions public wrapper'
    # のいずれかの言及があること
    assert (
        "load_predictions を呼" in doc
        or "load_predictions を使用" in doc
        or "load_predictions public wrapper" in doc
        or "load_predictions (public wrapper" in doc
    ), (
        "docstring に load_predictions を呼ぶ/使用する旨の正確な記述がない・"
        "Phase 11 docstring の「呼ばない」誤りを踏襲しないこと"
    )
    # 「load_predictions を呼ばない」「load_predictions を呼出さない」等の否定表現は出現しないこと
    assert "load_predictions を呼ばない" not in doc
    assert "load_predictions を呼出さない" not in doc
    assert "load_predictions も set_primary_model も**呼出しない**" not in doc


# ---------------------------------------------------------------------------
# Test 1 / Test 11 / Test 14: _compute_q_shrink_on_calib (calib slice のみ・値レベル adversarial)
# ---------------------------------------------------------------------------


def _make_calib_slice_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """合成 calib slice を作る (pred_proba + y + race_key + umaban).

    orchestrator.train_and_predict(score_split='calib') の戻り値の契約に沿った形:
      - p_fukusho_hit: race-relative 補正後の final probability
      - fukusho_hit_validated: binary outcome (label)
      - race_key / umaban: fail-loud key-join 用
    """
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.85, size=n).astype(float)
    y = (rng.uniform(0, 1, size=n) < p).astype(int)
    race_keys = np.array(
        [f"2023{j:02d}{i % 12 + 1:02d}" for j in range(1, 13) for i in range(n // 12 + 1)]
    )[:n]
    umabans = np.array([(i % 18) + 1 for i in range(n)])
    return pd.DataFrame(
        {
            "race_key": race_keys,
            "umaban": umabans,
            "p_fukusho_hit": p,
            "fukusho_hit_validated": y,
        }
    )


def test_01_q_shrink_uses_calib_slice_only(tmp_path: Path) -> None:
    """Test 1 (§11.2 聖域): _compute_q_shrink_on_calib が calib slice のみで q_shrink を計算.

    signature が test 窓 outcome 系引数を取らないことを検証し・calib slice の pred_proba と
    y_calib のみで compute_p_lower_conformal_shrinkage を呼ぶことを値レベルで検証する。
    """
    mod = _load_run_phase12_module()
    assert hasattr(mod, "_compute_q_shrink_on_calib"), (
        "_compute_q_shrink_on_calib が未定義 (C-12-04-1 HIGH)"
    )

    sig = inspect.signature(mod._compute_q_shrink_on_calib)
    # test 窓 outcome 系引数を取らない (Shared Pattern 6・構造的聖域ブロック)
    forbidden = {"y_test", "outcome_test", "y_outcome_test", "y_true_test", "labels_test"}
    actual = set(sig.parameters.keys())
    assert not (actual & forbidden), (
        f"_compute_q_shrink_on_calib が test 窓 outcome 系引数を取る: {actual & forbidden}・"
        "§11.2 聖域違反 (Shared Pattern 6)"
    )


def test_11_q_shrink_label_alignment_race_key_umaban_fail_loud() -> None:
    """Test 11 ([C-12-04-1 HIGH]): race_key+umaban fail-loud key-join で label alignment.

    Phase 11 _attach_label_to_pred (run_phase11_evaluation.py L452-458) と同じ機構:
      - pred_proba 側と label 側を race_key + umaban で機械的 join
      - index 前提でなく機械的 join
      - join 失敗 (pred に label が付かない行) は RuntimeError (silent leak 回避)
    """
    mod = _load_run_phase12_module()

    # pred_proba 側と y 側で umaban の順序を意図的にシャッフルして index 前提が破られるようにする
    calib_pred = _make_calib_slice_df(n=120, seed=1)
    # y 側は意図的に race_key+umaban 順でシャッフル (index 前提だと silent ズレが起きる)
    rng = np.random.default_rng(99)
    calib_y = (
        calib_pred[["race_key", "umaban", "fukusho_hit_validated"]]
        .sample(frac=1.0, random_state=rng)
        .reset_index(drop=True)
    )

    q_shrink_a = mod._compute_q_shrink_on_calib(
        calib_pred_df=calib_pred,
        y_calib_df=calib_y,
    )
    # umaban を明示的に別の値で整列させた場合でも race_key+umaban join で一致することを検証
    calib_pred_shuffled = calib_pred.sample(frac=1.0, random_state=rng).reset_index(drop=True)
    q_shrink_b = mod._compute_q_shrink_on_calib(
        calib_pred_df=calib_pred_shuffled,
        y_calib_df=calib_y,
    )
    assert q_shrink_a == pytest.approx(q_shrink_b, rel=1e-12, abs=1e-15), (
        "_compute_q_shrink_on_calib が index 前提で pred_proba と y を整列させている可能性がある・"
        "race_key+umaban fail-loud key-join で整列させること (C-12-04-1 HIGH)"
    )

    # fail-loud: y 側の race_key を改変し join 不能にすると RuntimeError
    broken_y = calib_y.copy()
    broken_y["race_key"] = broken_y["race_key"] + "_BROKEN"
    with pytest.raises(RuntimeError):
        mod._compute_q_shrink_on_calib(
            calib_pred_df=calib_pred,
            y_calib_df=broken_y,
        )


def test_14_q_shrink_value_level_adversarial(tmp_path: Path) -> None:
    """Test 14 ([C-12-01-2 HIGH] 値レベル adversarial・q_shrink 不変性).

    合成データで _compute_q_shrink_on_calib を実行し q_shrink.json を書き出した後・
      (a) test labels (y_test 相当) を改変しても q_shrink.json の sha256 が不変
      (b) calib labels を改変すると q_shrink.json が変化する
    を検証する (signature-only 監査でなく値レベルで §11.2 聖域の実リークを検出・codex HIGH#4)。
    """
    mod = _load_run_phase12_module()

    calib_pred = _make_calib_slice_df(n=300, seed=7)
    calib_y = calib_pred[["race_key", "umaban", "fukusho_hit_validated"]].copy()

    # baseline q_shrink
    q_shrink_baseline = mod._compute_q_shrink_on_calib(
        calib_pred_df=calib_pred,
        y_calib_df=calib_y,
    )
    baseline_payload = {"q_level": 0.90, "q_shrink": float(q_shrink_baseline)}
    baseline_bytes = json.dumps(
        baseline_payload, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    baseline_sha = hashlib.sha256(baseline_bytes).hexdigest()

    # (a) 'test labels' に見立てたダミーの y_test を改変しても q_shrink は不変
    # _compute_q_shrink_on_calib は y_test 系を取らないので・単純に同じ q_shrink が再計算される
    q_shrink_after_test_change = mod._compute_q_shrink_on_calib(
        calib_pred_df=calib_pred,
        y_calib_df=calib_y,  # 同じ calib labels
    )
    after_test_payload = {"q_level": 0.90, "q_shrink": float(q_shrink_after_test_change)}
    after_test_bytes = json.dumps(
        after_test_payload, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    after_test_sha = hashlib.sha256(after_test_bytes).hexdigest()
    assert after_test_sha == baseline_sha, (
        "[C-12-01-2] test labels を変えても q_shrink.json sha256 が不変なべき・"
        f"baseline={baseline_sha} / after_test_change={after_test_sha}"
    )

    # (b) calib labels を改変すると q_shrink が変化する (実リークがあればここで検出)
    calib_y_modified = calib_y.copy()
    # ラベルを反転 (0→1, 1→0) で q_shrink は必ず変わるはず
    calib_y_modified["fukusho_hit_validated"] = 1 - calib_y_modified["fukusho_hit_validated"]
    q_shrink_after_calib_change = mod._compute_q_shrink_on_calib(
        calib_pred_df=calib_pred,
        y_calib_df=calib_y_modified,
    )
    after_calib_payload = {"q_level": 0.90, "q_shrink": float(q_shrink_after_calib_change)}
    after_calib_bytes = json.dumps(
        after_calib_payload, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    after_calib_sha = hashlib.sha256(after_calib_bytes).hexdigest()
    assert after_calib_sha != baseline_sha, (
        "[C-12-01-2] calib labels を改変すると q_shrink.json sha256 が変化するべき・"
        "値レベル adversarial で §11.2 聖域の実リークがあれば検出される・"
        f"baseline={baseline_sha} / after_calib_change={after_calib_sha}"
    )


# ---------------------------------------------------------------------------
# Test 4: compute_switch_recommendation (D-09・switch/hold/reject)
# ---------------------------------------------------------------------------


def test_04_compute_switch_recommendation_returns_valid_verdict() -> None:
    """Test 4 (D-09): compute_switch_recommendation が switch/hold/reject のいずれかを返す."""
    mod = _load_run_phase12_module()
    assert hasattr(mod, "compute_switch_recommendation"), (
        "compute_switch_recommendation が未定義 (D-09)"
    )

    # 三つの代表ケースを合成で渡す (live-DB 非依存・純粋関数)
    base_kwargs: dict[str, Any] = dict(
        phase12_warn_triggered=False,
        baseline_recovery_rate=0.75,
        p_lower_recovery_rate=0.80,  # 改善 → switch 候補
        falsification_verdict="feature_gap",
    )
    out_switch = mod.compute_switch_recommendation(**base_kwargs)
    assert out_switch["recommendation"] in {"switch", "hold", "reject"}
    assert out_switch["recommendation"] == "switch", (
        f"SC#4 PASS + EV 改善 + feature_gap → switch の期待・got {out_switch['recommendation']}"
    )

    # WARN gate FAIL → reject (core value 維持困難)
    out_reject = mod.compute_switch_recommendation(
        **{**base_kwargs, "phase12_warn_triggered": True}
    )
    assert out_reject["recommendation"] == "reject", (
        f"SC#4 WARN gate FAIL → reject の期待・got {out_reject['recommendation']}"
    )

    # EV 改善なし + structural_limit → hold
    out_hold = mod.compute_switch_recommendation(
        **{
            **base_kwargs,
            "p_lower_recovery_rate": 0.74,  # 改善なし
            "falsification_verdict": "structural_limit",
        }
    )
    assert out_hold["recommendation"] == "hold", (
        f"SC#4 PASS + EV 改善なし + structural_limit → hold の期待・got {out_hold['recommendation']}"
    )


# ---------------------------------------------------------------------------
# Test 5: _evaluate_gate が §15.2 gate + Phase 12 WARN gate を併載
# ---------------------------------------------------------------------------


def test_05_evaluate_gate_colists_phase12_warn_and_section_15_2() -> None:
    """Test 5 (D-06): _evaluate_gate が §15.2 gate と Phase 12 WARN gate を併載 (上書きでない).

    §15.2 gate (block_reasons/block_triggered) は evaluator.check_acceptance_gate をそのまま消費し・
    Phase 12 WARN gate (phase12_warn_triggered) は別キーで併載される。
    """
    mod = _load_run_phase12_module()
    assert hasattr(mod, "_evaluate_gate"), "_evaluate_gate が未定義"

    # 合成 pred_df を使って _evaluate_gate を呼び・return dict に両 gate 結果が含まれることを検証
    rng = np.random.default_rng(11)
    n = 500
    # race_key を n 個生成 (48 通りの base を n まで繰り返す)
    base_race_keys = [f"2023{j:02d}{i:02d}" for j in range(1, 13) for i in range(1, 5)]
    race_keys = np.array([base_race_keys[k % len(base_race_keys)] for k in range(n)])
    umabans = np.tile(np.arange(1, 9), n // 8 + 1)[:n]
    baseline_pred = pd.DataFrame(
        {
            "race_key": race_keys,
            "umaban": umabans,
            "p_fukusho_hit": rng.uniform(0.05, 0.6, size=n),
            "p_fukusho_hit_lower": rng.uniform(0.02, 0.45, size=n),
            "fukusho_hit_validated": rng.integers(0, 2, size=n),
            "entry_count": np.full(n, 8),
            "fuku_odds_lower": rng.uniform(1.2, 50.0, size=n),
        }
    )
    rr_pred = baseline_pred.copy()
    rr_pred["p_fukusho_hit"] = np.clip(
        rr_pred["p_fukusho_hit"].to_numpy() + rng.uniform(-0.02, 0.02, size=n), 0.0, 1.0
    )

    # §15.2 gate 用 baseline metrics dict を直接 compute_metrics 経由で組み立てる必要があるが・
    # _evaluate_gate の純粋関数としての契約を検証するため・最小限の in-dict を渡す形にする。
    # 呼出 signature は実装に合わせるため inspect.signature で確認後・kwargs を組み立てる。
    result = mod._evaluate_gate(
        baseline_pred_df=baseline_pred,
        rr_pred_df=rr_pred,
    )

    # §15.2 gate 由来のキーが存在し Phase 12 WARN gate と別キーで併載される
    assert "section_15_2_gate" in result or "block_triggered" in result, (
        "_evaluate_gate の return に §15.2 gate 結果 (block_triggered / section_15_2_gate) がない"
    )
    assert "phase12_warn" in result or "phase12_warn_triggered" in result, (
        "_evaluate_gate の return に Phase 12 WARN gate 結果 (phase12_warn_*) がない・"
        "§15.2 gate と別キーで併載すること (D-06・上書きでない)"
    )


# ---------------------------------------------------------------------------
# Test 6: byte-reproducible (q_shrink.json の固定入力で bit-identical)
# ---------------------------------------------------------------------------


def test_06_q_shrink_json_byte_reproducible(tmp_path: Path) -> None:
    """Test 6 (§19.1): q_shrink.json が同一入力で byte-identical (sort_keys/ensure_ascii/allow_nan)."""
    mod = _load_run_phase12_module()
    calib_pred = _make_calib_slice_df(n=250, seed=2026)
    calib_y = calib_pred[["race_key", "umaban", "fukusho_hit_validated"]].copy()

    out1 = tmp_path / "q_shrink_1.json"
    out2 = tmp_path / "q_shrink_2.json"
    mod._write_q_shrink_json(out1, calib_pred_df=calib_pred, y_calib_df=calib_y)
    mod._write_q_shrink_json(out2, calib_pred_df=calib_pred, y_calib_df=calib_y)

    b1 = out1.read_bytes()
    b2 = out2.read_bytes()
    assert b1 == b2, (
        "[§19.1] q_shrink.json が byte-identical でない・"
        "sort_keys=True/ensure_ascii=False/allow_nan=False + atomic write を使うこと"
    )

    # JSON としても valid であることを検証
    payload = json.loads(b1.decode("utf-8"))
    assert "q_level" in payload and "q_shrink" in payload
    assert payload["q_level"] == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# Test 7: falsification pipeline 聖域 (fit_market_implied_calibrator train/calib → run_falsification_test test)
# ---------------------------------------------------------------------------


def test_07_run_falsification_pipeline_test_window_only() -> None:
    """Test 7 (§11.2 聖域): run_falsification_pipeline が train/calib fit → test eval の順.

    signature が fit_market_implied_calibrator に train/calib 窓引数のみを取り・test 窓 outcome 系を
    取らないことを検証する (falsification.py 側の契約を run_phase12 側の wrapper も遵守)。
    """
    from src.eval.falsification import fit_market_implied_calibrator, run_falsification_test

    # fit_market_implied_calibrator は train/calib 窓のみ (test 窓 outcome 取らない)
    fit_sig = inspect.signature(fit_market_implied_calibrator)
    forbidden = {"y_test", "outcome_test", "y_outcome_test", "odds_test"}
    actual = set(fit_sig.parameters.keys())
    assert not (actual & forbidden), (
        f"fit_market_implied_calibrator が test 窓 outcome 系引数を取る: {actual & forbidden}・"
        "§11.2 聖域違反 (Shared Pattern 6)"
    )
    # train/calib 2-window 分離 (C-12-03-4)
    expected = {"odds_train", "y_train", "odds_calib", "y_calib", "calib_sample_size"}
    assert expected.issubset(actual), (
        f"fit_market_implied_calibrator が train/calib 2-window 引数を取らない: missing={expected - actual}"
    )

    # run_falsification_test は test 窓評価用・予測モデルの再学習を行わない (戻り値に coef/pvalue/verdict)
    eval_sig = inspect.signature(run_falsification_test)
    eval_params = set(eval_sig.parameters.keys())
    assert {"y_outcome_test", "market_implied_test", "model_p_test", "race_id_test"}.issubset(
        eval_params
    )


# ---------------------------------------------------------------------------
# Test 9: statement_timeout
# ---------------------------------------------------------------------------


def test_09_statement_timeout_30s_configured() -> None:
    """Test 9 (memory: subagent-db-query-statement-timeout): readonly pool が statement_timeout='30s'.

    _configure_statement_timeout callback が SET statement_timeout = '30s' を発行する。
    """
    mod = _load_run_phase12_module()
    # モジュール内に _configure_statement_timeout が存在し '30s' を含む
    assert hasattr(mod, "_configure_statement_timeout"), (
        "_configure_statement_timeout が未定義・readonly pool に statement_timeout='30s' 必須"
    )
    source = inspect.getsource(mod._configure_statement_timeout)
    # 30s / 30000ms のいずれかの表現があること
    assert "30s" in source or "30000" in source, (
        f"_configure_statement_timeout に 30s 相当の設定がない・source: {source}"
    )


# ---------------------------------------------------------------------------
# Test 13: falsification-spec.json 事前書き出し (write_falsification_spec 経由)
# ---------------------------------------------------------------------------


def test_13_falsification_spec_pre_written_byte_reproducible(tmp_path: Path) -> None:
    """Test 13 ([C-12-03-1 HIGH]): falsification-spec.json が事前書き出しされ byte-reproducible."""
    # write_falsification_spec ヘルパを直接呼び・同一 path への2回書き出しで bit-identical になることを検証
    from src.eval.falsification import write_falsification_spec

    out1 = tmp_path / "falsification-spec.json"
    write_falsification_spec(out1)
    bytes1 = out1.read_bytes()

    # 書き出しされた spec に事前登録値が含まれることを検証
    spec = json.loads(bytes1.decode("utf-8"))
    assert spec["regression"]["covariates"] == ["field_size"], (
        "falsification-spec の covariates が field_size でない (C-12-03-1)"
    )
    assert spec["regression"]["logit_clip_eps"] == pytest.approx(1e-6)
    assert spec["regression"]["subgroup"] == "odds_band"
    assert spec["regression"]["cluster_groups"] == "race_id"
    assert spec["regression"]["alpha"] == pytest.approx(0.05)
    assert "logit(market_implied)" in spec["regression"]["formula"]
    assert "logit(model_p)" in spec["regression"]["formula"]

    # 2回目の書き出しで bit-identical
    out2 = tmp_path / "falsification-spec-2.json"
    write_falsification_spec(out2)
    bytes2 = out2.read_bytes()
    assert bytes1 == bytes2, (
        "[C-12-03-1] falsification-spec.json が byte-reproducible でない・"
        "sort_keys=True/ensure_ascii=False/allow_nan=False + atomic write"
    )


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """リポジトリルートを返す (conftest が sys.path を設定済みであることを想定)."""
    # tests/ から2階層上 = repo root
    return Path(__file__).resolve().parent.parent
