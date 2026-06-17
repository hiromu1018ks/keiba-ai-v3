"""src/utils/calibrator.py の smoke テスト（成功基準#4 / §15.2）。

REVIEWS HIGH #3 を直接検証する:
- ``fit_prefit_calibrator`` が ``train_max_date >= race_dates_calib.min()`` で
  ``ValueError``（``AssertionError`` ではない）を raise する。
- ``python -O`` で実行しても raise が生存することをサブプロセスで検証する。
- ``CalibratedClassifierCV`` が ``cv='prefit'`` で構成される（§15.2 KFold shuffle 回避）。
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from datetime import date

import numpy as np
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier

from src.utils.calibrator import fit_prefit_calibrator


def _dummy_data(n: int = 200):
    rng = np.random.default_rng(42)
    X = rng.normal(size=(n, 3))
    y = (X[:, 0] + 0.5 * rng.normal(size=n) > 0).astype(int)
    return X, y


# --- 正常系 ---


def test_calib_after_train_passes():
    """train_max_date < calib.min() の正常ケースで fit が成功する。"""
    X, y = _dummy_data(200)

    # train 用 base estimator を事前 fit
    base = GradientBoostingClassifier(n_estimators=10, max_depth=2, random_state=0)
    base.fit(X[:120], y[:120])

    X_calib = X[120:200]
    y_calib = y[120:200]
    calib_dates = pd_date_range_starting("2024-04-01", 80)

    cal = fit_prefit_calibrator(
        base_estimator=base,
        X_calib=X_calib,
        y_calib=y_calib,
        race_dates_calib=calib_dates,
        train_max_date=date(2024, 3, 31),
        method="isotonic",
    )

    assert cal is not None
    assert cal.cv == "prefit", f"cv='prefit' ではない: {cal.cv}"


def test_prefit_cv():
    """戻り calibrator の .cv == 'prefit'（§15.2）。"""
    X, y = _dummy_data(150)
    base = DummyClassifier(strategy="prior")
    base.fit(X[:100], y[:100])
    cal = fit_prefit_calibrator(
        base_estimator=base,
        X_calib=X[100:150],
        y_calib=y[100:150],
        race_dates_calib=pd_date_range_starting("2024-04-01", 50),
        train_max_date=date(2024, 3, 31),
        method="sigmoid",  # dummy 推定器で sigmoid の方が安定
    )
    assert cal.cv == "prefit"


# --- HIGH #3 直接検証: ValueError を raise（AssertionError でなく） ---


def test_calib_before_train_raises_valueerror():
    """train_max_date >= calib.min() で ValueError を raise（D-17・HIGH #3）。

    AssertionError ではなく ValueError であることを検証する。
    """
    X, y = _dummy_data(150)
    base = DummyClassifier(strategy="prior")
    base.fit(X[:100], y[:100])

    # train_max_date が calib.min() と等しい（>= 違反）
    calib_dates = pd_date_range_starting("2024-04-01", 50)

    with pytest.raises(ValueError, match="strictly later"):
        fit_prefit_calibrator(
            base_estimator=base,
            X_calib=X[100:150],
            y_calib=y[100:150],
            race_dates_calib=calib_dates,
            train_max_date=date(2024, 4, 1),  # == calib.min()
            method="sigmoid",
        )


def test_calib_survives_python_optimized_flag():
    """``python -O`` で実行しても guard が raise することをサブプロセス検証（HIGH #3）。

    ``assert`` 版だと ``-O`` で無効化されて exit 0 になってしまう。
    """
    code = (
        "import sys\n"
        "from datetime import date\n"
        "import pandas as pd\n"
        "from sklearn.dummy import DummyClassifier\n"
        "from src.utils.calibrator import fit_prefit_calibrator\n"
        "base = DummyClassifier(strategy='prior')\n"
        "import numpy as np\n"
        "X = np.zeros((10, 2)); y = np.zeros(10, dtype=int)\n"
        "base.fit(X, y)\n"
        "try:\n"
        "    fit_prefit_calibrator(base, X, y, "
        "race_dates_calib=pd.date_range('2024-04-01', periods=10), "
        "train_max_date=date(2024, 5, 1), method='sigmoid')\n"
        "    sys.exit(0)\n"  # raise されなかった = バグ
        "except ValueError:\n"
        "    sys.exit(2)\n"  # 期待: ValueError で exit 2
        "except AssertionError:\n"
        "    sys.exit(3)\n"  # assert 版なら -O で到達不能だが念のため
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 2, (
        f"python -O で ValueError が raise されなかった（HIGH #3 違反）: "
        f"exit={result.returncode}, stdout={result.stdout}, stderr={result.stderr}"
    )


def test_calib_raises_is_valueerror_not_assertion():
    """リグレッションガード: ソースに assert 文がなく raise ValueError がある（HIGH #3）。"""
    from src.utils import calibrator as cal_mod

    src = inspect.getsource(cal_mod.fit_prefit_calibrator)
    assert_lines = [ln for ln in src.splitlines() if ln.lstrip().startswith("assert ")]
    assert assert_lines == [], (
        f"fit_prefit_calibrator に assert 文が含まれる（HIGH #3 違反・python -O で削除される）: {assert_lines}"
    )
    assert "raise ValueError" in src, "raise ValueError が含まれない（HIGH #3 違反）"


def test_calibrator_uses_estimator_arg_not_base_estimator():
    """sklearn 1.9.0 の ``estimator=`` 引数（legacy ``base_estimator=`` ではない）を使用する。"""
    from src.utils import calibrator as cal_mod

    src = inspect.getsource(cal_mod)
    assert "estimator=" in src, "sklearn 1.9.0 の estimator= 引数が使われていない"
    assert "base_estimator=" not in src.replace(
        "base_estimator,", ""
    ).replace("base_estimator:", ""), (
        "legacy base_estimator= 引数が使われている（sklearn 1.9.0 では非推奨）"
    )


# --- helper ---


def pd_date_range_starting(start: str, n: int):
    import pandas as pd

    return pd.date_range(start, periods=n)
