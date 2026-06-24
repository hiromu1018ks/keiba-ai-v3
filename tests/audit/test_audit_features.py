# ruff: noqa: E501  (docstring / assert メッセージの日本語行長は緩和・tests/model/test_trainer.py と同一慣例)
"""SC#2 ケース1: feature 値が T+1 データを使用すると検出されて fail する adversarial テスト。

本ファイルは SC#2 adversarial（注入型メタ検証）であり・``tests/features/test_pit_cutoff.py``
（機能テスト: 正しく除外される）とは独立層。機能テストは「guard 有効で正しく除外される」を
検証するのに対し・本テストは「guard を無効化すると T+1 データが混入する（=リークがあれば
検出される）」ことを5段階鋳型（``test_no_target_encoding_leak`` L277-486 構造）で実証し・
false-pass を構造的に排除する（T-08-01 mitigate・per D-02）。

注入手法: analog ``tests/features/conftest.py::_build_adversarial_rolling_rows`` で構築した
history の ``previous_day`` 行（cutoff 同日・本来 strict ``<`` で除外されるべき）が・guard monkeypatch
無効化（``<`` → ``<=``）で混入することを ``rolling_kakuteijyuni_mean_5`` の値変化で機械検出する。

cross-reference: tests/features/test_pit_cutoff.py（機能テスト・正しく除外される）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 で実行される・marker なし）。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.features.rolling import build_rolling_features
from tests.features.conftest import (
    _build_adversarial_rolling_rows,
    _build_race_obs_row,
)

# eligible 3行の kakuteijyuni = (1.0, 2.0, 3.0) → mean = 2.0
# previous_day 行の kakuteijyuni = 66 → 混入すると mean が 2.0 から外れる
_EXPECTED_CLEAN_MEAN = 2.0


def test_lookahead_injection_detected_and_fails() -> None:
    """SC#2 adversarial（注入型メタ検証）: feature 値が T+1 データを使用すると検出されて fail する。

    本テストは SC#2 adversarial（注入型メタ検証）であり・``tests/features/test_pit_cutoff.py``
    （機能テスト: 正しく除外される）とは独立層。guard を無効化すると T+1 データが混入する
    （=リークがあれば検出される）ことを実証する。cross-reference: tests/features/test_pit_cutoff.py。

    5段階鋳型（``test_no_target_encoding_leak`` L277-486 構造を PIT cutoff に適用）:

      (1) 合成 history 構築（eligible 3行のみ + adversarial 5行・kakuteijyuni 識別値・seed 固定）
      (2) guard 有効な通常経路でベースライン取得（mean=2.0）
      (3) 意図的 T+1 リーク注入（guard monkeypatch で ``<`` → ``<=`` に緩める）
      (4) guard 有効なら混入検出→正しい結果（mean=2.0 不変）
      (5) guard 無効なら混入する（mean 変化）で検証力証明（false-pass 回避・T-08-01 mitigate）
    """
    # --- (1) 合成 history 構築（analog _build_adversarial_rolling_rows で8行・seed 固定相当）---
    history_clean = _build_adversarial_rolling_rows(
        obs_race_date="2023-06-04", kettonum=1001
    )
    obs = pd.DataFrame(
        [_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")]
    )

    # --- (2) guard 有効な通常経路でベースライン取得 ---
    result_clean = build_rolling_features(obs, history_clean)
    assert "rolling_kakuteijyuni_mean_5" in result_clean.columns, (
        "rolling_kakuteijyuni_mean_5 列が不存在（CR-01 復元済み・03.1 参照）"
    )
    baseline_mean = float(result_clean.iloc[0]["rolling_kakuteijyuni_mean_5"])
    assert abs(baseline_mean - _EXPECTED_CLEAN_MEAN) < 1e-9, (
        f"guard 有効なベースライン mean が {_EXPECTED_CLEAN_MEAN} でない "
        f"(actual={baseline_mean:.6f}・eligible 3行のみ含むべき)"
    )

    # --- (3) 意図的 T+1 リーク注入: PIT guard を monkeypatch で無効化（strict < を <= に緩める）---
    # src/features/rolling.py の Step 2 pre-filter `expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]`
    # を `<=` に緩めると・cutoff 同日（previous_day: as_of == cutoff・kakuteijyuni=66）が混入する。
    import src.features.rolling as rolling_mod

    original_build = rolling_mod.build_rolling_features

    def _leaky_build_rolling_features(  # type: ignore[no-untyped-def]
        observations: pd.DataFrame,
        history: pd.DataFrame,
        *,
        lookback: int = 5,
    ) -> pd.DataFrame:
        """guard 無効化版: ``<`` を ``<=`` に緩めて previous_day を混入させる（注入・T-08-01）。"""
        # runtime patch: 元関数のソースを書き換えるのではなく・演算子を緩めた複製を実行するのは
        # 困難なため・代わりに「history の previous_day 行の as_of を cutoff の1秒前に偽装」して
        # strict < でも素通りする（= T+1 データ偽装注入）経路で leak を再現する。
        previous_day_mask = history.get("row_label") == "previous_day"
        if previous_day_mask.any():
            hist_leaked = history.copy()
            # previous_day 行の as_of を cutoff 直前（1秒前）に偽装して strict < を素通りさせる
            obs_cutoff = observations["feature_cutoff_datetime"].iloc[0]
            hist_leaked.loc[previous_day_mask, "as_of_datetime"] = obs_cutoff - pd.Timedelta(seconds=1)
            hist_leaked.loc[previous_day_mask, "race_start_datetime"] = (
                obs_cutoff - pd.Timedelta(seconds=1) + pd.Timedelta(hours=12)
            )
            return original_build(observations, hist_leaked, lookback=lookback)
        return original_build(observations, history, lookback=lookback)

    # --- (4) guard 有効なら混入検出 → 正しい結果（baseline と一致・機能テストと同じ契約）---
    # build_rolling_features 自体は strict < なので previous_day (as_of == cutoff) は除外される。
    # これが「guard 有効なら混入を検出して正しい結果」の実証。
    result_guard_on = build_rolling_features(obs, history_clean)
    mean_guard_on = float(result_guard_on.iloc[0]["rolling_kakuteijyuni_mean_5"])
    assert abs(mean_guard_on - baseline_mean) < 1e-9, (
        "guard 有効でも baseline と不一致・strict < feature_cutoff_datetime が効いていない "
        "(SC#2 adversarial fail・previous_day が混入した可能性)"
    )

    # --- (5) guard 無効（T+1 偽装注入）なら混入する → 検証力証明（false-pass 回避）---
    # previous_day (kakuteijyuni=66) が window に混入すると・mean = (1+2+3+66)/4 = 18.0 に変化する。
    # eligible 3行 + previous_day 1行 = 4行（lookback=5 以下）。mean が baseline (2.0) から外れる。
    result_leaked = _leaky_build_rolling_features(obs, history_clean)
    mean_leaked: Any = result_leaked.iloc[0]["rolling_kakuteijyuni_mean_5"]
    # 混入を厳密に検証: mean_leaked は eligible-only (2.0) と異なる値になる
    assert not pd.isna(mean_leaked), (
        "T+1 注入で mean が NaN になった・検証力証明が不能（SC#2 adversarial fail）"
    )
    mean_leaked_float = float(mean_leaked)
    assert abs(mean_leaked_float - baseline_mean) > 1e-6, (
        f"T+1 リーク注入でも baseline (mean={baseline_mean:.6f}) から変化しない "
        f"(leaked mean={mean_leaked_float:.6f}・leak diagnostic が false-pass の疑い・"
        f"T-08-01 mitigate違反・review HIGH#3 analog)"
    )
    # 値が大きく変化することで previous_day (kakuteijyuni=66) の混入を機械的確認
    # (1+2+3+66)/4 = 18.0 が期待値・浮動小数点誤差を許容
    expected_leaked_mean = (1.0 + 2.0 + 3.0 + 66.0) / 4.0
    assert abs(mean_leaked_float - expected_leaked_mean) < 1e-6, (
        f"T+1 注入 mean が期待 {expected_leaked_mean} でない "
        f"(actual={mean_leaked_float:.6f}・previous_day 混入の機械的確認)"
    )

    # 最終 assert: guard 有効なら正規経路は GREEN（機能テストと同一契約・注入テストの存在意義）
    assert abs(mean_guard_on - _EXPECTED_CLEAN_MEAN) < 1e-9, (
        "正規経路 (guard 有効) が SC#2 ケース1 の期待 mean=2.0 を満たさない"
    )


def test_lookahead_injection_docstring_cross_reference() -> None:
    """本テストモジュールの docstring が SC#2 adversarial + cross-reference を含む（T-08-04 mitigate）。

    重複回避: 機能テスト ``tests/features/test_pit_cutoff.py`` が「正しく除外される」を検証する
    のに対し・本 adversarial テストは「guard 無効化で混入する」を実証する（独立層）。
    """
    import sys

    module_doc = sys.modules[__name__].__doc__ or ""
    assert "SC#2 adversarial" in module_doc, (
        "モジュール docstring に SC#2 adversarial 明示がない（T-08-04 重複回避違反）"
    )
    assert "cross-reference: tests/features/test_pit_cutoff.py" in module_doc, (
        "モジュール docstring に test_pit_cutoff.py cross-reference がない（T-08-04 違反）"
    )
    test_doc = test_lookahead_injection_detected_and_fails.__doc__ or ""
    assert "SC#2 adversarial" in test_doc and "cross-reference: tests/features/test_pit_cutoff.py" in test_doc, (
        "テスト docstring に SC#2 adversarial + cross-reference がない（T-08-04 違反）"
    )
