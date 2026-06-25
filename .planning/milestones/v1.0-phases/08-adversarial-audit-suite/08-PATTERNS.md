# Phase 8: Adversarial Audit Suite - Pattern Map

**Mapped:** 2026-06-24
**Files analyzed:** 10（新規ファイル群・`tests/audit/` 4件 + conftest/init + scripts + src/audit/report.py + reports 2件）
**Analogs found:** 10 / 10（全ファイルに exact/role-match analog あり）

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/audit/__init__.py` | test (package marker) | — | `tests/features/__init__.py` 等 | exact（慣例） |
| `tests/audit/conftest.py` | test (fixtures) | 合成データ注入 | `tests/features/conftest.py` | exact（合成 DataFrame 注入ヘルパー鋳型そのもの） |
| `tests/audit/test_audit_features.py` | test (adversarial・注入型メタ) | 合成データ注入→fail 実証 | `tests/model/test_trainer.py::test_no_target_encoding_leak` | exact（SC#2 adversarial 鋳型） |
| `tests/audit/test_audit_label.py` | test (adversarial・注入型メタ) | 合成データ注入→fail 実証 | `tests/model/test_trainer.py::test_no_target_encoding_leak`（鋳型）＋ `tests/test_label_reconcile.py`（payout 突合 mock） | exact（鋳型）＋ role-match（payout 対象） |
| `tests/audit/test_audit_split.py` | test (adversarial・注入型メタ) | 合成データ注入→raise 実証 | `tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak` | exact（注入→raise 既存実装） |
| `tests/audit/test_audit_ui_csv.py` | test (adversarial・構造検査) | AST 検査 / presence assert | `tests/ui/test_readonly_guarantee.py`（AST SQL 検査）＋ `tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps`（presence assert） | exact（両 analog の組み合わせ） |
| `scripts/run_reproducibility_smoke.py` | utility (orchestrator) | subprocess orchestrate (batch) | `scripts/run_train_predict.py`（`--check-reproduce`・`main()->int`・try/except PsycopgError/finally pool.close 構造） | role-match（薄い orchestrator） |
| `src/audit/report.py` | service (report 生成) | transform (md+json 分離出力) | `src/ev/report.py`（REPORT_COLUMNS・generate_report・_atomic_write_text・sort_keys） | exact（md+json 分離 DRY パターン） |
| `reports/08-audit.md` | config (成果物・人間確認) | file-I/O（生成対象） | `reports/05-backtest.md`（md 人間確認版） | exact（reports/ 慣例） |
| `reports/08-audit.json` | config (成果物・機械消費) | file-I/O（生成対象・byte-reproducible） | `reports/05-backtest.json`（json sort_keys 機械消費版） | exact（reports/ 慣例） |

## Pattern Assignments

### `tests/audit/test_audit_features.py` (test, adversarial・lookahead 注入)

**Analog:** `tests/model/test_trainer.py::test_no_target_encoding_leak` (L277-486)
**Role analog:** `tests/features/conftest.py::_build_adversarial_rolling_rows` / `_build_two_observation_rolling_rows`

このファイルは SC#2 ケース1（lookahead 注入検出）の独立 adversarial メタテスト。`test_no_target_encoding_leak` の「意図的リーク注入で DEMONSTRABLY fail を実証」の5段階鋳型を PIT cutoff に適用する。

**Imports パターン**（analog `tests/model/test_trainer.py` L16-39）:
```python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.rolling import build_rolling_features  # 検査対象
from src.features.conftest_helpers import (  # 直接再利用
    _build_adversarial_rolling_rows,
    _build_race_obs_row,
)
```

**adversarial 5段階鋳型**（analog `test_no_target_encoding_leak` L423-486）:
```python
# (1) 合成データ構築（制御可能・seed 固定）— tests/features/conftest.py の builder 再利用
history_clean = _build_adversarial_rolling_rows(obs_race_date="2023-06-04")
obs = pd.DataFrame([_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")])

# (2) 通常経路（リークなし）でベースライン取得
result_clean = build_rolling_features(obs, history_clean)
assert abs(result_clean.iloc[0]["rolling_kakuteijyuni_mean_5"] - 2.0) < 1e-9  # eligible 3行のみ

# (3) 意図的リーク注入（guard の monkeypatch 無効化 / 偽装 as_of）
#     previous_day 行の as_of を cutoff 直前に偽装（本来除外されるべきが混入）

# (4) guard 有効なら混入検出→正しい結果・無効なら assert が fail
result_leaked = build_rolling_features(obs, history_leaked)
assert abs(result_leaked.iloc[0]["rolling_kakuteijyuni_mean_5"] - 2.0) < 1e-9, (
    "lookahead 注入が検出されず T+1 データが混入（SC#2 adversarial fail）"
)
```

**docstring 慣例**（重複回避・analog `test_no_target_encoding_leak` L278-283 の明示的 intent）:
```python
def test_lookahead_injection_detected_and_fails():
    """SC#2 adversarial（注入型メタ検証）: feature 値が T+1 データを使用すると検出されて fail する。

    本テストは SC#2 adversarial（注入型メタ検証）であり・`test_pit_cutoff`（機能テスト:
    正しく除外される）とは独立層。guard を無効化すると混入する（=リークがあれば検出される）
    ことを実証する。cross-reference: tests/features/test_pit_cutoff.py。
    """
```

---

### `tests/audit/test_audit_label.py` (test, adversarial・payout 正欠損注入)

**Analog:** `tests/model/test_trainer.py::test_no_target_encoding_leak`（鋳型）＋ `tests/test_label_reconcile.py`（payout 突合 mock cursor パターン）

このファイルは SC#2 ケース2（payout 払戻対象正の馬が label に欠落検出）の独立 adversarial。`test_no_target_encoding_leak` の注入→fail 鋳型を payout reconciliation に適用し・`test_label_reconcile` の `_mock_cursor` パターンで合成 label/payout 不整合を注入する。

**Imports パターン**（analog `tests/test_label_reconcile.py` L32-54）:
```python
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.etl.label_reconcile import _check_payout_recall, reconcile_against_payout
from src.etl.quality_gate import CheckResult
```

**mock cursor / 合成 DataFrame 注入パターン**（analog `tests/test_label_reconcile.py` L61-87, L213-247）:
```python
# analog の _mock_cursor: SQL 部分文字列マッチで fetchone 戻り値を切り替え
def _mock_cursor(fetch_map: dict[str, object]) -> MagicMock:
    cur = MagicMock()
    cur._fetch_map = fetch_map
    def _execute(sql: str, *args, **kwargs):
        cur._last_sql = sql
        return cur
    cur.execute.side_effect = _execute
    def _fetchone():
        sql = getattr(cur, "_last_sql", "")
        for key, val in cur._fetch_map.items():
            if key in sql:
                return val
        return (0,)
    cur.fetchone.side_effect = _fetchone
    return cur

# adversarial 適用: payout 正の馬（umaban=7）を label から欠落させる注入
# recall SQL が不一致件数 N>0 を返す mock → _check_payout_recall.passed is False
cur = _mock_cursor({"fukusho_hit_validated = 0": (1,)})  # 欠落1件注入
r = _check_payout_recall(cur)
assert r.passed is False, "payout 正欠損が検出されない（SC#2 adversarial fail）"
assert r.detail.get("count") == 1
```

**注入→fail 適用**（`test_no_target_encoding_leak` L457-465 の「threshold assert で検証力証明」パターンを payout recall に翻訳）:
```python
# verdict 集計で passed=False → verdict='fail'（analog test_label_reconcile L555-568）
# 合成 label/payout で「正の馬の欠落」を直接注入し end-to-end で fail を実証
```

---

### `tests/audit/test_audit_split.py` (test, adversarial・fold race_id 共有注入)

**Analog:** `tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak` (L208-234)

このファイルは SC#2 ケース3（fold の train/test が race_id を共有する検出）。既存の `test_get_bt_race_ids_raises_on_leak` が「意図的に train_end==test_start で R2 を共有→ValueError」の注入→raise パターンを既に実現済み。SC#2 専用 docstring で再定式化し・既存テストへの cross-reference を含む。

**Imports パターン**（analog `tests/utils/test_group_split.py` L9-17）:
```python
from __future__ import annotations

import pandas as pd
import pytest

from src.utils.group_split import BT_WINDOWS, BTWindow, get_bt_race_ids
```

**注入→raise パターン**（analog `test_get_bt_race_ids_raises_on_leak` L208-234・そのまま再利用可能）:
```python
def test_fold_race_id_shared_detected_and_raises():
    """SC#2 adversarial: fold の train/test が race_id を共有すると ValueError で検出される。

    本テストは SC#2 adversarial（注入型メタ検証）。cross-reference:
    tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak（既存・同一注入パターン）。
    SC#2 要件「3ケースそれぞれ独立 adversarial」を docstring で明示するため再定式化。
    """
    leak_races = pd.DataFrame({
        "race_id": ["R0", "R1", "R2", "R3"],
        "race_date": pd.to_datetime(
            ["2022-12-30", "2022-12-31", "2023-01-01", "2023-01-02"]
        ),
        "race_start_datetime": pd.to_datetime(
            ["2022-12-30", "2022-12-31", "2023-01-01", "2023-01-02"]
        ),
    })
    # train_end == test_start で R2 を意図的に共有（リーク注入）
    bad_bt = BTWindow(
        name="BT-LEAK",
        train_start="2022-12-30",
        train_end="2023-01-01",   # R2 を含む
        test_start="2023-01-01",  # R2 を含む（共有）
        test_end="2023-01-02",
        window_type="expanding",
    )
    with pytest.raises(ValueError, match="race_id"):
        get_bt_race_ids(leak_races, bad_bt)
```

**注記（RESEARCH A3）:** ケース3は既存 `test_get_bt_race_ids_raises_on_leak` が注入→fail を実現済みのため・adversarial 新設の付加価値は限定的。SC#2 専用 docstring で再定式化することを推奨（重複回避のため既存テストへの cross-reference を含む）。

---

### `tests/audit/test_audit_ui_csv.py` (test, adversarial・UI 書込経路 / スタンプ欠落検出)

**Analog:** `tests/ui/test_readonly_guarantee.py`（AST SQL 検査）＋ `tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps`（presence assert）

このファイルは D-06（Phase 7 継承の UI/CSV 対抗的監査）。2つの analog を組み合わせる: (a) AST で SQL 文字列リテラルの書き込み/DDL キーワード検出、(b) presence assert で再現性スタンプの存在検証。

**Imports パターン**（analog `tests/ui/test_readonly_guarantee.py` L17-20, `tests/ui/test_csv_columns.py` L13）:
```python
from __future__ import annotations

import ast
from pathlib import Path

from src.ui.csv_columns import PREDICTION_CSV_COLUMNS  # presence assert 対象
```

**AST SQL リテラル抽出パターン**（analog `tests/ui/test_readonly_guarantee.py` L44-64・そのまま再利用可能）:
```python
def _extract_sql_literals(tree: ast.AST) -> list[str]:
    """AST から cur.execute / cursor.execute Call の第一引数の str 定数を抽出する。
    REVIEW LOW-2: SQL 文字列リテラルのみを検査（comment/docstring/変数名の false positive 回避）。
    """
    sql_literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            sql_literals.append(first_arg.value)
    return sql_literals
```

**presence assert パターン**（analog `tests/ui/test_csv_columns.py` L65-77）:
```python
def test_prediction_csv_has_all_stamps():
    """再現性スタンプ4項目が含まれる（§19.1 聖域）."""
    for stamp in (
        "odds_snapshot_policy",
        "odds_snapshot_at",
        "model_version",
        "feature_snapshot_id",
    ):
        assert stamp in PREDICTION_CSV_COLUMNS, f"再現性スタンプ {stamp!r} がない (§19.1 聖域違反)"
```

**adversarial 拡張（注入→fail メタ検証）:** 一時的に INSERT を含むダミー .py を `tmp_path` に配置→AST 検査が fail することを実証（RESEARCH A5）。スタンプ欠落は `PREDICTION_CSV_COLUMNS` から1スタンプを除いた tuple で presence assert が fail することを実証。

---

### `tests/audit/conftest.py` (test fixtures, 合成 DataFrame 注入ヘルパー)

**Analog:** `tests/features/conftest.py` (L1-207)

このファイルは `tests/audit/` 共通の合成 DataFrame 注入ヘルパー。`tests/features/conftest.py` の `_build_se_history_row` / `_build_race_obs_row` / `_build_adversarial_rolling_rows` パターンを再利用・拡張する。PII なし・ID のみ（analog L14 慣例）。

**ヘッダ/docstring パターン**（analog `tests/features/conftest.py` L1-15）:
```python
"""Phase 8 audit 共通 fixtures / synthetic DataFrame builder.

仕様（Plan 08-01・SC#2 adversarial 注入ヘルパー）:

  - ``_build_*_row``: 合成 label/payout/race 行 builder
    （test_label_reconcile.py / test_fukusho_label.py パターン踏襲）。
  - adversarial 注入ヘルパー: SC#2 の3ケース（lookahead/payout正欠損/fold共有）で
    共通して使う合成データ構築関数。

合成行は ID のみを使用し、実馬名・騎手名等の PII は含まない（T-03-03 accept 踏襲）。
"""

from __future__ import annotations
from unittest.mock import MagicMock
import pandas as pd
import pytest
```

**合成行 builder パターン**（analog L28-84・`_build_se_history_row` / `_build_race_obs_row` の `**overrides` 機構）:
```python
def _build_label_row(race_key: str, umaban: int, **overrides) -> dict:
    """合成 label 行（test_fukusho_label.py analog）。デフォルトは正常出走馬。
    ``**overrides`` で任意カラムを上書き（注入制御用）。
    """
    row: dict = {
        "race_key": race_key,
        "umaban": umaban,
        "fukusho_hit_validated": 1,
        # ... 既定カラム ...
    }
    row.update(overrides)
    return row
```

---

### `scripts/run_reproducibility_smoke.py` (utility, subprocess orchestrate)

**Analog:** `scripts/run_train_predict.py`（`--check-reproduce` フラグ L257-280・`main()->int` 構造 L218-411・try/except/finally）

このファイルは SC#3（フルパイプライン固定 seed 再現）の薄い orchestrator。新規フルパイプライン runner は作らず・既存 CLI（`run_train_predict --check-reproduce`・`run_backtest --check-reproduce --synthetic`）と pytest を subprocess で束ねる（D-03）。

**ヘッダ/sys.path ガード パターン**（analog `scripts/run_train_predict.py` L46-61）:
```python
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# scripts/ から src.* を import するためリポジトリルートを sys.path に追加。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_reproducibility_smoke")
```

**subprocess orchestrate パターン**（RESEARCH L381-410・analog の `main()->int` + 失敗時 sys.exit 構造）:
```python
def main(argv: list[str] | None = None) -> int:
    """SC#3: snapshot→train→predict→backtest→eval が固定 seed で同一結果を再現することを確認。

    Phase 4 SC#4 の bit-identical インフラ（seed=42 + num_threads=1 + FIXED_REPRODUCE_TS）を
    orchestrate する薄いスクリプト。新規フルパイプライン runner は作らない（D-03）。
    """
    steps = [
        # (1) Phase 4 SC#4: 両モデル bit-identical（合成データ・--no-write-db で高速）
        (["uv", "run", "python", "scripts/run_train_predict.py",
          "--check-reproduce", "--no-write-db"], "SC#4 bit-identical (train/predict)"),
        # (2) calibrator bit-identical pytest
        (["uv", "run", "pytest",
          "tests/model/test_calibrator.py::test_reproduce_bit_identical", "-q"],
         "calibrator bit-identical"),
        # (3) backtest --check-reproduce --synthetic（合成BT窓・決定論的）
        (["uv", "run", "python", "scripts/run_backtest.py",
          "--synthetic", "--bt-filter", "BT-1", "--check-reproduce", "--no-write-db"],
         "backtest bit-identical"),
        # (4) audit adversarial テスト群（SC#2 注入ケース全て GREEN）
        (["uv", "run", "pytest", "tests/audit/", "-q"], "SC#2 adversarial tests"),
    ]
    for cmd, desc in steps:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            logger.error("FAIL: %s", desc)
            return 1
        logger.info("PASS: %s", desc)
    logger.info("SC#3 reproducibility smoke: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**bit-identical 検証プリミティブ**（analog `src/model/orchestrator.py::_assert_deterministic` L758-820 が確立済み・`np.array_equal` で bit-identical）:
```python
# analog の核心: seed=42 + num_threads=1 + FIXED_REPRODUCE_TS で2回 train_and_predict
# → p_fukusho_hit 列が np.array_equal (bit-identical) になることを検証
# 本スクリプトはこれを subprocess で呼ぶのみ（再実装しない）
```

---

### `src/audit/report.py` (service, md+json 分離 report 生成)

**Analog:** `src/ev/report.py` (L1-308)

このファイルは `reports/08-audit.{md,json}` 生成ロジック。`src/ev/report.py` の DRY パターン（REPORT_COLUMNS 定数外部化・md+json 分離・`_atomic_write_text`・`sort_keys=True`・presence assert）を再利用する。

**ヘッダ/imports パターン**（analog `src/ev/report.py` L26-33）:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model.artifact import _atomic_write_text  # 原子的書込（再利用）
```

**REPORT_COLUMNS 定数外部化パターン**（analog L41-53・presence assert [LOW-05] 対応）:
```python
# report の列契約（LOW-05: report.md 列ヘッダ・report.json キーと 1:1）
AUDIT_SURFACE_COLUMNS: tuple[str, ...] = (
    "surface",          # サーフェス名（fukusho_label / payout_reconcile / cutoff / split / ...）
    "sc_id",            # SC#1/#2/#3 のどれに対応
    "existing_tests",   # 既存テストファイル・関数
    "adversarial_test", # tests/audit/ の新設テスト（あれば）
    "status",           # COVERED / ADVERSARIAL / GAP
    "evidence",         # GREEN 証明の根拠
)
```

**md+json 分離生成パターン**（analog L176-274・`generate_report` 関数）:
```python
def generate_audit_report(
    surface_rows: list[dict[str, Any]],
    *,
    output_dir: str | Path = "reports",
    known_limitations: list[str] | None = None,
    full_suite_result: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """監査結果を reports/08-audit.{md,json} に出力する（D-01/D-04/D-05）。"""
    out_dir = Path(output_dir)
    md_path = out_dir / "08-audit.md"
    json_path = out_dir / "08-audit.json"

    # BACK-04 analog: 決定論的 sort（辞書順・seed 非依存）
    sorted_rows = sorted(surface_rows, key=lambda r: str(r.get("surface", "")))

    # --- Markdown（人間確認用）---
    md_lines: list[str] = []
    md_lines.append("# Phase 8 Adversarial Audit Report (TEST-01 / SC#1・SC#2・SC#3)\n\n")
    md_lines.append("## サーフェス別カバレッジマップ (SC#1 #1-#8)\n\n")
    md_lines.append(_format_surface_table_md(sorted_rows))
    md_lines.append("\n\n")
    # Known Limitations（D-05）
    md_lines.append("## Known Limitations (\"Looks Done But Isn't\" honest 開示)\n\n")
    for lim in (known_limitations or []):
        md_lines.append(f"- {lim}\n")
    _atomic_write_text(md_path, "".join(md_lines))

    # --- JSON（byte-reproducible・sort_keys=True・ensure_ascii=False）---
    json_payload = json.dumps(
        {
            "surface_map": sorted_rows,
            "constants": {"AUDIT_SURFACE_COLUMNS": list(AUDIT_SURFACE_COLUMNS)},
            "known_limitations": known_limitations or [],
            "full_suite_result": full_suite_result or {},
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    _atomic_write_text(json_path, json_payload)
    return (md_path, json_path)
```

**定数注記パターン**（analog L59-90・`ODDS_POLICY_FIXED_NOTE` / `NO_WINNER_OVERRIDE_NOTE` 等の定数 text 外部化）:
```python
# D-05 Known Limitations の定数（honest 開示・memory fukusho-recovery-070 整合）
RECOVERY_CEILING_NOTE: str = (
    "回収率天井 ~0.65-0.70: odds-free 1-A モデルの構造的限界（LightGBM 0.7022・CatBoost 0.6808）。"
    "閾値調整では改善しない・Phase 1-B（odds 特徴量）か評価リフレームで対処。"
    "memory fukusho-recovery-070-structural-ceiling 整合。"
)
CALIBRATION_BL_INFERIOR_NOTE: str = (
    "Calibration BL 劣位: 主モデル(LGB calibration_max_dev=0.2308)が BL-1(0.0014)/BL-4 に劣位。"
    "Phase 4 SC#2 で確定・Phase 6 キャリブ指標再設計（quantile/ECE/MCE 併記）の文脈。"
)
ODDS_JODDS_REVERIFICATION_NOTE: str = (
    "odds JODDS再検証 subject: Phase 5 実データ backtest 25件完走だが・odds 正確性は"
    "JODDS取得完了後に再検証。manual-only 分離。"
)
```

---

### `reports/08-audit.{md,json}` (config/成果物)

**Analog:** `reports/05-backtest.{md,json}`（reports/ 慣例・md 人間確認 + json byte-reproducible 分離）

生成対象であり・コードから生成される。analog は `reports/05-backtest.md`（markdown 表・注記セクション構造）と `reports/05-backtest.json`（`sort_keys=True`・`comparison_table`/`metrics`/`constants`/`notes` 階層）。

**構造（analog `reports/05-backtest.md` 構成要素を 08-audit 用に翻訳）:**
- `# Phase 8 Adversarial Audit Report`（タイトル・TEST-01/SC 印）
- `## サーフェス別カバレッジマップ`（SC#1 #1-#8 の8サーフェス表・AUDIT_SURFACE_COLUMNS 順）
- `## SC#1/#2/#3 対応表`（各 SC と既存/adversarial テストの対応）
- `## Known Limitations`（D-05・回収率天井/Calibration劣位/odds再検証）
- `## フルスイート GREEN 証明`（D-04・KEIBA_SKIP_DB_TESTS unset・全 requires_db 実行・0 skipped）

## Shared Patterns

### 合成 DataFrame 注入ヘルパー（SC#2 adversarial 共通基盤）
**Source:** `tests/features/conftest.py::_build_adversarial_rolling_rows` / `_build_two_observation_rolling_rows` / `_build_se_history_row` / `_build_race_obs_row` (L28-188)
**Apply to:** `tests/audit/conftest.py`・`tests/audit/test_audit_features.py`・`tests/audit/test_audit_label.py`
```python
# analog の核心: 制御可能な seed・識別可能な kakuteijyuni 値で rolling 結果が
# eligible 行のみ含むことを機械的検出
def _build_adversarial_rolling_rows(obs_race_date="2023-06-04", kettonum=1001) -> pd.DataFrame:
    # 8行（5行 adversarial + 3行 eligible）・各 row kakuteijyuni 区別値
    # CR-01 後は kakuteijyuni を識別値に使用（timediff/babacd 系統は rolling から削除済）
```

### mock cursor パターン（payout recall 注入）
**Source:** `tests/test_label_reconcile.py::_mock_cursor` (L61-87)
**Apply to:** `tests/audit/test_audit_label.py`
```python
def _mock_cursor(fetch_map: dict[str, object]) -> MagicMock:
    """SQL 部分文字列マッチで fetchone() の戻り値を返すモック cursor。"""
    cur = MagicMock()
    cur._fetch_map = fetch_map
    def _execute(sql, *args, **kwargs):
        cur._last_sql = sql
        return cur
    cur.execute.side_effect = _execute
    def _fetchone():
        sql = getattr(cur, "_last_sql", "")
        for key, val in cur._fetch_map.items():
            if key in sql:
                return val
        if sql.strip().upper().startswith("SELECT"):
            return (0,)
        return None
    cur.fetchone.side_effect = _fetchone
    return cur
```

### md+json 分離 reports 生成（DRY・全 reports 共通）
**Source:** `src/ev/report.py::generate_report` (L176-274) + `src/model/artifact.py::_atomic_write_text`
**Apply to:** `src/audit/report.py`・`reports/08-audit.{md,json}`
```python
# 核心ルール:
# (1) REPORT_COLUMNS 定数で列定義外部化（LOW-05 presence assert 対応）
# (2) Markdown は人間確認用・json は byte-reproducible（sort_keys=True・ensure_ascii=False）
# (3) _atomic_write_text で原子的書込（src/model/artifact.py 再利用）
# (4) 決定論的 sort（辞書順・seed 非依存・BACK-04 analog）
# (5) 定数 text は外部化（ODDS_POLICY_FIXED_NOTE 等の慣例）
```

### scripts/run_*.py CLI 慣例（全 run スクリプト共通）
**Source:** `scripts/run_train_predict.py` (L46-88, L218-411)
**Apply to:** `scripts/run_reproducibility_smoke.py`
```python
# (1) sys.path ガード: _REPO_ROOT = Path(__file__).resolve().parent.parent
# (2) logging.basicConfig + logger = logging.getLogger("run_<name>")
# (3) main(argv: list[str] | None = None) -> int 構造
# (4) try/except PsycopgError / finally pool.close（DB 触る場合）
# (5) if __name__ == "__main__": sys.exit(main())
# (6) argparse で --check-reproduce / --no-write-db / --synthetic 等のフラグ
```

### bit-identical 再現性検証プリミティブ（SC#3/SC#4 共通）
**Source:** `src/model/orchestrator.py::_assert_deterministic` (L758-820) + `tests/model/test_calibrator.py::test_reproduce_bit_identical` (L137-173)
**Apply to:** `scripts/run_reproducibility_smoke.py`（subprocess で呼ぶのみ・再実装しない）
```python
# 核心プリミティブ: np.array_equal(pred1, pred2) で bit-identical 検証
# 固定要素: seed=42 + num_threads=1 + FIXED_REPRODUCE_TS（datetime(2026,6,20)）
# LGB_INIT_PARAMS: seed/deterministic/force_col_wise/bagging_seed/feature_fraction_seed/num_threads
# CB_INIT_PARAMS: random_seed/has_time/thread_count
```

### DB-test skip policy（KEIBA_SKIP_DB_TESTS・D-04 ゲート基盤）
**Source:** `tests/conftest.py::pytest_collection_modifyitems` (L66-78)
**Apply to:** `tests/audit/`（新規 adversarial は DB 不要・合成データ中心で設計 → skip 対象外）
```python
def pytest_collection_modifyitems(config, items):
    """KEIBA_SKIP_DB_TESTS=1 の時のみ requires_db マークを skip。
    デフォルト（unset/CI）では skip しない。実 DB 未接続では Settings() の
    validation error で fail（policy: fail-by-default unless KEIBA_SKIP_DB_TESTS=1）。"""
    skip_db = os.environ.get("KEIBA_SKIP_DB_TESTS") == "1"
    if not skip_db:
        return
    skip_marker = pytest.mark.skip(reason="KEIBA_SKIP_DB_TESTS=1 set")
    for item in items:
        if "requires_db" in item.keywords:
            item.add_marker(skip_marker)
```

## No Analog Found

なし。Phase 8 の全新規ファイル（`tests/audit/` 4件 + conftest + scripts + src/audit/report.py + reports 2件）に・Phase 1-7 で確立された exact/role-match analog が存在する。Phase 8 は「新規の仕組みを発明しない・既存パターンの組み合わせと集約」で完結する（RESEARCH "Key insight" 整合）。

## Metadata

**Analog search scope:**
- `tests/`（model/features/utils/ui/ev/conftest.py 配下の adversarial・注入・AST 検査テスト群）
- `scripts/`（run_train_predict.py・run_backtest.py の `--check-reproduce`/`--synthetic` フラグと CLI 慣例）
- `src/ev/report.py`（md+json 分離 reports DRY パターン）
- `src/model/orchestrator.py`（`_assert_deterministic` bit-identical 検証）
- `reports/`（05-backtest/06-evaluation の md+json 慣例）
- `tests/conftest.py`（KEIBA_SKIP_DB_TESTS skip policy）

**Files scanned:** 12（上記 analog ファイル全て直接 Read で精査）
**Pattern extraction date:** 2026-06-24
**Confidence:** HIGH — 全 analog がコードベース直接精査済み・RESEARCH.md の cross-reference と一致

## PATTERN MAPPING COMPLETE

**Phase:** 8 - adversarial-audit-suite
**Files classified:** 10
**Analogs found:** 10 / 10

### Coverage
- Files with exact analog: 9（`tests/audit/__init__.py` は慣例含めると10）
- Files with role-match analog: 1（`scripts/run_reproducibility_smoke.py` は薄い orchestrator で role-match・既存 CLI を束ねる新規形態）
- Files with no analog: 0

### Key Patterns Identified
- **adversarial（注入型メタ）テストの5段階鋳型** — `test_no_target_encoding_leak`（合成データ→ベースライン→リーク注入→注入版で fail→検証力証明）が SC#2 の3ケース全てに再利用可能
- **mock cursor による payout 注入** — `test_label_reconcile::_mock_cursor` の SQL 部分文字列マッチで `_check_payout_recall` の passed=False を実証
- **AST SQL リテラル検査 + presence assert** — `test_readonly_guarantee`（書き込み/DDL 検出）＋ `test_csv_columns`（スタンプ存在）の組み合わせで D-06 UI/CSV 監査
- **md+json 分離 reports DRY** — `src/ev/report.py`（REPORT_COLUMNS 定数外部化・`_atomic_write_text`・`sort_keys=True`・presence assert[LOW-05]）が `src/audit/report.py` に直接再利用可能
- **既存 CLI orchestrate の薄いスクリプト** — `run_train_predict --check-reproduce` + `run_backtest --synthetic --check-reproduce` + pytest を subprocess で束ねる（新規 runner 不要・D-03）
- **KEIBA_SKIP_DB_TESTS fail-by-default policy** — conftest.py の skip 機構が D-04 unset 全実行ゲートの基盤・adversarial テストは DB 不要で skip 対象外

### File Created
`/Users/hart/develop/keiba-ai-v3/.planning/phases/08-adversarial-audit-suite/08-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files. 全新規ファイルに analog が存在し・RESEARCH.md の「既存パターンの組み合わせと集約で完結・新規の仕組みを発明しない」を裏付け。
