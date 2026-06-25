"""SC#3 合成層: 固定 seed で合成データの bit-identical 再現性を確認する薄い orchestrator (per D-03).

REVIEW WR-04 (スコープ開示・ファイル名は不変): 本スクリプトのファイル名は
``run_reproducibility_smoke.py`` だが・現状 (Phase 08 時点) で実際にカバーするのは
**calibrator bit-identical 1 関数のみ** (test_reproduce_bit_identical) と SC#2 adversarial
(tests/audit/) である。「フルパイプラインの再現性 smoke」を名乗るには検証力が薄く・
trainer bit-identical 群 (tests/model/test_trainer.py) は該当テスト 0 件のため除外している
(NC-03 参照)。trainer に bit-identical テストが追加された場合は step 1 に戻すこと。
ユーザーは本スクリプトを「SC#3 = full pipeline reproducibility 済み」と誤推論しないこと
(現状は calibrator N=1 の thin orchestrator)。

Phase 4 SC#4 の bit-identical インフラ (seed=42 + num_threads=1 + FIXED_REPRODUCE_TS) を
DB 不要 pytest で orchestrate する。新規フルパイプライン runner は作らない (keep it simple・
重複回避)。

live-DB 必須の再現 CLI (run_train_predict --check-reproduce / run_backtest --check-reproduce) は
本スクリプトでは呼ばず Plan 08-03 checkpoint が実行する:
  - run_train_predict は --synthetic flag 非存在で Settings() + make_pool + load_labels により
    live-DB 必須
  - run_backtest --synthetic --check-reproduce は readonly_pool=None でラベル未結合のまま
    orchestrator L341 で raise ValueError で非零 exit するため

SC#3 の合成層は以下の2 step を subprocess で順次実行し・いずれかが非零 exit なら即座に return 1:
  (1) calibrator bit-identical pytest (test_reproduce_bit_identical・live-DB 不要・合成データ)
  (2) tests/audit/ (SC#2 adversarial 全 GREEN・Plan 08-01 成果物・KEIBA_SKIP_DB_TESTS=1 でも
      実行される DB 不要テスト)

NC-03: trainer bit-identical 群 (tests/model/test_trainer.py の -k "reproduce or
bit_identical or deterministic") は現状 (commit eff76c6 時点) 該当テスト0件・collect-only
で確認済みのため step から除外する。将来 trainer に bit-identical テストが追加された場合は
steps に戻すこと (WR-04 開示の検証力拡張計画)。
"""

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


# SC#3 合成層の step 定義 (D-03・NC-03 対応・live-DB 不要 pytest のみ)。
# 各要素は (cmd, description) の tuple。subprocess.run で順次実行する。
# live-DB 必須 CLI (run_train_predict --check-reproduce / run_backtest --check-reproduce) は
# 08-03 checkpoint が実行するため本リストには含めない (F-02/F-03)。
_STEPS: list[tuple[list[str], str]] = [
    (
        [
            "uv",
            "run",
            "pytest",
            "tests/model/test_calibrator.py::test_reproduce_bit_identical",
            "-q",
        ],
        "SC#4 calibrator bit-identical (test_reproduce_bit_identical・live-DB 不要・合成データ)",
    ),
    (
        ["uv", "run", "pytest", "tests/audit/", "-q"],
        "SC#2 adversarial tests (tests/audit/・Plan 08-01 成果物・DB 不要)",
    ),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を parse する。

    ``--step`` は単一 step 実行用のデバッグオプション (省略時は全 step を順次実行)。
    """
    parser = argparse.ArgumentParser(
        description=(
            "SC#3 合成層 reproducibility smoke: 固定 seed で合成データの bit-identical "
            "再現性を DB 不要 pytest で確認 (D-03)"
        ),
    )
    parser.add_argument(
        "--step",
        type=int,
        default=None,
        help="単一 step のみ実行 (1-based・デバッグ用・省略時は全 step)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """SC#3 合成層: 合成データの固定 seed 再現を確認。

    2 step を subprocess で順次実行し・いずれかが非零 exit なら即座に ``return 1``。
    全 step PASS で ``return 0``。live-DB 必須 CLI は 08-03 が実行する。
    """
    args = parse_args(argv)

    steps = _STEPS
    if args.step is not None:
        # 1-based index で単一 step 実行 (デバッグ用)
        if not (1 <= args.step <= len(_STEPS)):
            logger.error("--step は 1..%d の範囲で指定すること (got %s)", len(_STEPS), args.step)
            return 1
        steps = [_STEPS[args.step - 1]]

    for cmd, desc in steps:
        logger.info("RUN: %s", desc)
        # REVIEW WR-03: capture_output=True で子プロセス出力を補足し・失敗時のみ
        # 末尾 ~2000 文字を logger に dump する (CI での buffer overflow / truncate 対策)。
        # 成功時は出力を破棄し・GREEN のままだと spam にならないよう配慮。
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FAIL: %s (returncode=%s)", desc, result.returncode)
            # 失敗原因の可視化のため stdout/stderr の末尾 ~2000 文字を dump (debug 性向上)。
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            logger.error("stdout (tail 2000 chars):\n%s", stdout_tail)
            logger.error("stderr (tail 2000 chars):\n%s", stderr_tail)
            return 1
        logger.info("PASS: %s", desc)

    logger.info("SC#3 reproducibility smoke (synthetic layer): ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
