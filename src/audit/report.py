# ruff: noqa: E501  (長い docstring / note 文字列を保持するため行長は緩和)
"""Phase 8 adversarial audit report 生成 (D-01/D-05・src/ev/report.py DRY パターン再利用).

Plan 08-02 で ``scripts/run_reproducibility_smoke.py`` (SC#3 合成層) と対で ``reports/08-audit.{md,json}``
を生成する出力層。サーフェス別カバレッジマップ (SC#1 #1-#8 + 詜価指標計算)・SC#1/#2/#3 対応表・
Known Limitations を md (人間確認) と json (byte-reproducible・機械消費) に分離出力する。

**設計の核心 (D-01/D-05・LOW-05 analog):**

1. **AUDIT_SURFACE_COLUMNS 定数外部化 (LOW-05 analog)**: 列契約を tuple 定数で定義し・
   ``report.md`` の列ヘッダと ``report.json`` の ``surface_map`` row キーが 1:1 になることを
   ``generate_audit_report`` 末尾の presence assert で機械検証する (grep 否定でなく presence assert)。
2. **md + json 分離 (src/ev/report.py DRY)**: Markdown は人間確認用・json は
   ``sort_keys=True``・``ensure_ascii=False`` で byte-reproducible。``_atomic_write_text`` で
   原子的書込 (partial-failure 抑止)。
3. **Known Limitations honest 開示 (D-05)**: 回収率天井・Calibration BL 劣位・odds JODDS再検証
   を定数 (``RECOVERY_CEILING_NOTE`` 等) で強制し・md と json の両方に出力 (隠蔽構造的に不可)。
4. **決定論的 sort (BACK-04 analog)**: SURFACE_ROWS は定義順 (SC#1 #1-#8 → 補足 → 評価指標)。
   json は ``sort_keys=True`` で byte-reproducible。

参照: 08-02-PLAN.md Task 2 / 08-PATTERNS.md (src/ev/report.py analog) /
      reports/06-evaluation.json (数値根拠) / REQUIREMENTS.md L65 TEST-01.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model.artifact import _atomic_write_text

# ---------------------------------------------------------------------------
# 列契約定数 (LOW-05 analog・md 列ヘッダと json キーを 1:1 に保持)
# ---------------------------------------------------------------------------
AUDIT_SURFACE_COLUMNS: tuple[str, ...] = (
    "surface",          # サーフェス名 (fukusho_label / payout_reconcile / cutoff / split / ...)
    "sc_id",            # SC#1/#2/#3 のどれに対応するか
    "existing_tests",   # 既存テストファイル・関数
    "adversarial_test", # tests/audit/ の新設 adversarial テスト (あれば)
    "status",           # COVERED / ADVERSARIAL / COVERED+ADVERSARIAL / GAP
    "evidence",         # GREEN 証明の根拠・数値参照
)

# ---------------------------------------------------------------------------
# Known Limitations 定数 (D-05・memory fukusho-recovery-070-structural-ceiling 整合)
# ---------------------------------------------------------------------------
# 数値根拠: reports/06-evaluation.json
#   - backtest_summary.by_model: lightgbm recovery_rate=0.7021532541 / catboost=0.6807827217
#   - comparison_table: lightgbm calibration_max_dev=0.2307692308 / bl1=0.001425964
RECOVERY_CEILING_NOTE: str = (
    "回収率天井 ~0.65-0.70: odds-free 1-A モデルの構造的限界 (LightGBM 0.7022・CatBoost 0.6808)。"
    "閾値調整では改善しない・Phase 1-B (odds 特徴量) か評価リフレームで対処。"
    "memory fukusho-recovery-070-structural-ceiling 整合。"
)
CALIBRATION_BL_INFERIOR_NOTE: str = (
    "Calibration BL 劣位: 主モデル (LGB calibration_max_dev=0.2308) が BL-1 (0.0014)/BL-4 に劣位。"
    "Phase 4 SC#2 で確定・Phase 6 キャリブ指標再設計 (quantile/ECE/MCE 併記) の文脈。"
)
ODDS_JODDS_REVERIFICATION_NOTE: str = (
    "odds JODDS再検証 subject: Phase 5 実データ backtest 25件完走だが・odds 正確性は"
    "JODDS取得完了後に再検証。manual-only 分離。"
)

KNOWN_LIMITATIONS: list[str] = [
    RECOVERY_CEILING_NOTE,
    CALIBRATION_BL_INFERIOR_NOTE,
    ODDS_JODDS_REVERIFICATION_NOTE,
]

# ---------------------------------------------------------------------------
# SC#1 #1-#8 サーフェス別既存テストマッピング (RESEARCH SC#1 マッピング表から転記)
# ---------------------------------------------------------------------------
# status: "COVERED" = 既存機能テストのみ / "ADVERSARIAL" = Plan 01 で adversarial 新設 /
#         "COVERED+ADVERSARIAL" = 両層
# SC#1 #1-#8 は REQUIREMENTS.md TEST-01 の明示サーフェス。補足カテゴリと評価指標計算を追加。
SURFACE_ROWS: list[dict[str, Any]] = [
    {
        "surface": "fukusho_label",
        "sc_id": "SC#1 #1",
        "existing_tests": "tests/test_fukusho_label.py (複勝払戻対象ラベル生成)",
        "adversarial_test": "",
        "status": "COVERED",
        "evidence": "REQUIREMENTS.md TEST-01 複勝ラベル・§10.5 払戻テーブル",
    },
    {
        "surface": "payout_reconcile",
        "sc_id": "SC#1 #2",
        "existing_tests": "tests/test_label_reconcile.py (_check_payout_recall・払戻テーブル突合 6検査)",
        "adversarial_test": "tests/audit/test_audit_label.py::test_payout_positive_missing_from_labels_detected",
        "status": "COVERED+ADVERSARIAL",
        "evidence": "SC#2 ケース2 payout 正欠損注入 adversarial (Plan 08-01)",
    },
    {
        "surface": "refund_handling",
        "sc_id": "SC#1 #3",
        "existing_tests": "tests/test_refund_accounting.py (取消/除外/中止・返金",
        "adversarial_test": "",
        "status": "COVERED",
        "evidence": "REQUIREMENTS.md TEST-01 取消/除外/中止・§10.5 返金",
    },
    {
        "surface": "odds_snapshot",
        "sc_id": "SC#1 #4",
        "existing_tests": "tests/ev/test_odds_snapshot.py (odds_snapshot_policy 時点固定・§11.2)",
        "adversarial_test": "",
        "status": "COVERED",
        "evidence": "REQUIREMENTS.md TEST-01 オッズ時点固定・§11.2/§19.1",
    },
    {
        "surface": "virtual_purchase",
        "sc_id": "SC#1 #5",
        "existing_tests": "tests/ev/test_metrics.py (compute_backtest_metrics: recovery_rate/refund/max_drawdown/effective_stake)",
        "adversarial_test": "",
        "status": "COVERED",
        "evidence": "REQUIREMENTS.md TEST-01 仮想購入・§11.4/§11.6 回収率",
    },
    {
        "surface": "feature_cutoff",
        "sc_id": "SC#1 #6",
        "existing_tests": "tests/features/test_pit_cutoff.py (feature_cutoff_datetime enforcement・merge_asof direction='backward'・§13.2/§13.4 禁止列)",
        "adversarial_test": "tests/audit/test_audit_features.py::test_lookahead_injection_detected_and_fails",
        "status": "COVERED+ADVERSARIAL",
        "evidence": "SC#2 ケース1 lookahead 注入 adversarial (Plan 08-01)",
    },
    {
        "surface": "race_id_split",
        "sc_id": "SC#1 #7",
        "existing_tests": "tests/utils/test_group_split.py (get_bt_race_ids・race_id disjoint guard・§8.4)",
        "adversarial_test": "tests/audit/test_audit_split.py::test_fold_race_id_shared_detected_and_raises",
        "status": "COVERED+ADVERSARIAL",
        "evidence": "SC#2 ケース3 fold race_id 共有注入 adversarial (Plan 08-01)",
    },
    {
        "surface": "class_normalization",
        "sc_id": "SC#1 #8",
        "existing_tests": "tests/test_class_normalization.py (クラス正規化)",
        "adversarial_test": "",
        "status": "COVERED",
        "evidence": "REQUIREMENTS.md TEST-01 クラス正規化",
    },
    # --- 補足カテゴリ (SC#1 明示リスト外だが TEST-01 が包括的にカバー) ---
    {
        "surface": "categorical_missing",
        "sc_id": "SC#1 supplement",
        "existing_tests": "tests/model/test_trainer.py (LightGBM category dtype・__MISSING__/__UNSEEN__ sentinel・CatBoost has_time・§14.3/§14.4/§14.5)",
        "adversarial_test": "tests/model/test_trainer.py::test_no_target_encoding_leak (Phase 4 adversarial 鋳型)",
        "status": "COVERED+ADVERSARIAL",
        "evidence": "REQUIREMENTS.md TEST-01 カテゴリ/欠損処理・§14.3 target encoding 禁止",
    },
    {
        "surface": "ui_csv_readonly",
        "sc_id": "D-06 (Phase 7 継承)",
        "existing_tests": "tests/ui/test_readonly_guarantee.py (AST SQL 検査)・tests/ui/test_csv_columns.py (presence assert・§19.1 スタンプ)",
        "adversarial_test": "tests/audit/test_audit_ui_csv.py (UI 書込/DDL SQL 混入検出 + 再現性スタンプ欠落検出)",
        "status": "COVERED+ADVERSARIAL",
        "evidence": "07-CONTEXT Deferred → Phase 8 委譲 (D-06)・TEST-01 対抗的監査",
    },
    # --- 評価指標計算サーフェス (F-05 対応・REQUIREMENTS.md L65 TEST-01 明示) ---
    {
        "surface": "evaluation_metrics",
        "sc_id": "TEST-01",
        "existing_tests": "tests/ev/test_metrics.py (compute_backtest_metrics: recovery_rate/refund/max_drawdown)・tests/model/test_evaluator.py (compute_metrics: calibration_max_dev/brier/logloss/auc/sum_p)・tests/model/test_evaluator_gate.py (評価指標 gate)",
        "adversarial_test": "",
        "status": "COVERED",
        "evidence": "REQUIREMENTS.md L65 TEST-01 評価指標計算・F-05 対応・§15.1/§15.2/§15.3",
    },
]

# ---------------------------------------------------------------------------
# SC#1/#2/#3 対応表データ
# ---------------------------------------------------------------------------
SC_CORRESPONDENCE: list[dict[str, str]] = [
    {
        "sc": "SC#1",
        "scope": "機能テスト (リーク防止 8サーフェス + 補足 + 評価指標)",
        "coverage": "既存476テストで COVERED (SURFACE_ROWS status 参照)",
        "evidence": "tests/{test_fukusho_label,test_label_reconcile,test_refund_accounting,test_odds_snapshot,test_pit_cutoff,test_group_split,test_class_normalization}.py + tests/model/test_trainer.py + tests/ui/ + tests/ev/test_metrics.py + tests/model/test_evaluator*.py",
    },
    {
        "sc": "SC#2",
        "scope": "対抗的 (注入型) テスト 3ケース (lookahead/payout正欠損/fold race_id共有)",
        "coverage": "ADVERSARIAL (Plan 08-01 で tests/audit/ に新設・KEIBA_SKIP_DB_TESTS=1 で GREEN)",
        "evidence": "tests/audit/test_audit_features.py (ケース1)・tests/audit/test_audit_label.py (ケース2)・tests/audit/test_audit_split.py (ケース3)・D-06 として tests/audit/test_audit_ui_csv.py (UI/CSV)",
    },
    {
        "sc": "SC#3",
        "scope": "フルパイプライン固定 seed 再現 (snapshot→train→predict→backtest→eval)",
        "coverage": "合成層: scripts/run_reproducibility_smoke.py (Plan 08-02)・live-DB 必須層: 08-03 checkpoint",
        "evidence": "合成層 = calibrator bit-identical pytest + tests/audit/ (DB 不要)・live-DB 必須 CLI (run_train_predict/run_backtest --check-reproduce) は 08-03 で人間承認付き実行",
    },
]

# ---------------------------------------------------------------------------
# Markdown 生成ヘルパ (analog src/ev/report.py::_format_comparison_table_md)
# ---------------------------------------------------------------------------

def _format_surface_table_md(rows: list[dict[str, Any]]) -> str:
    """SURFACE_ROWS を AUDIT_SURFACE_COLUMNS 順の markdown 表に変換する。

    tabulate 非依存 (src/ev/report.py L106-135 パターン)。
    """
    header = "| " + " | ".join(AUDIT_SURFACE_COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in AUDIT_SURFACE_COLUMNS) + " |"
    body_lines: list[str] = []
    for row in rows:
        cells: list[str] = []
        for col in AUDIT_SURFACE_COLUMNS:
            v = row.get(col)
            # markdown 表内の改行・パイプを空白化 (表崩れ防止)
            s = str(v) if v is not None else ""
            s = s.replace("\n", " ").replace("|", "/")
            cells.append(s)
        body_lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + body_lines)


def _format_sc_correspondence_md(rows: list[dict[str, str]]) -> str:
    """SC#1/#2/#3 対応表を markdown 表にする。"""
    cols = ("sc", "scope", "coverage", "evidence")
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    body: list[str] = []
    for row in rows:
        cells = []
        for c in cols:
            s = str(row.get(c, "")).replace("\n", " ").replace("|", "/")
            cells.append(s)
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + body)


# ---------------------------------------------------------------------------
# generate_audit_report (analog src/ev/report.py::generate_report L176-274)
# ---------------------------------------------------------------------------

def generate_audit_report(*, output_dir: str | Path = "reports") -> tuple[Path, Path]:
    """監査結果を ``reports/08-audit.{md,json}`` に出力する (D-01/D-05)。

    Parameters
    ----------
    output_dir : str | Path
        出力ディレクトリ (既定 ``'reports'``)。

    Returns
    -------
    tuple[Path, Path]
        ``(md_path, json_path)``。

    Notes
    -----
    - ``AUDIT_SURFACE_COLUMNS`` で md 列ヘッダと json キーを 1:1 に保つ (LOW-05 analog)。
    - json は ``sort_keys=True``・``ensure_ascii=False`` で byte-reproducible。
    - 末尾の presence assert で md ヘッダと json row キーが ``AUDIT_SURFACE_COLUMNS`` と
      1:1 であることを機械検証する (loud fail)。
    """
    out_dir = Path(output_dir)
    md_path = out_dir / "08-audit.md"
    json_path = out_dir / "08-audit.json"

    # --- Markdown (人間確認用) ---
    md_lines: list[str] = []
    md_lines.append("# Phase 8 Adversarial Audit Report (TEST-01 / SC#1・SC#2・SC#3)\n\n")
    md_lines.append("## サーフェス別カバレッジマップ (SC#1 #1-#8)\n\n")
    md_lines.append(_format_surface_table_md(SURFACE_ROWS))
    md_lines.append("\n\n")
    md_lines.append("## SC#1/#2/#3 対応表\n\n")
    md_lines.append(_format_sc_correspondence_md(SC_CORRESPONDENCE))
    md_lines.append("\n\n")
    md_lines.append("## Known Limitations (\"Looks Done But Isn't\" honest 開示)\n\n")
    for lim in KNOWN_LIMITATIONS:
        md_lines.append(f"- {lim}\n")
    md_lines.append("\n")
    md_lines.append("## フルスイート GREEN 証明 (D-04)\n\n")
    md_lines.append(
        "KEIBA_SKIP_DB_TESTS unset 全実行・全 requires_db 含む・0 skipped。"
        "詳細は checkpoint 08-03 (Plan 08-03) で実施。\n"
    )
    md_payload = "".join(md_lines)
    _atomic_write_text(md_path, md_payload)

    # --- JSON (byte-reproducible・sort_keys=True・ensure_ascii=False) ---
    json_payload = json.dumps(
        {
            "surface_map": SURFACE_ROWS,
            "constants": {"AUDIT_SURFACE_COLUMNS": list(AUDIT_SURFACE_COLUMNS)},
            "known_limitations": KNOWN_LIMITATIONS,
            "sc_correspondence": SC_CORRESPONDENCE,
            "full_suite_result": {"d04_checkpoint": "Plan 08-03 で実施"},
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    _atomic_write_text(json_path, json_payload)

    # --- presence assert (LOW-05 analog・md ヘッダと json キーが AUDIT_SURFACE_COLUMNS と 1:1) ---
    # md のサーフェステーブルヘッダ行 (最初の "| surface | sc_id | ..." 行) に全 column 名が
    # 含まれること。md 先頭行はレポートタイトル ("# Phase 8 ...") のため・表ヘッダを明示的に抽出。
    header_line = ""
    for line in md_payload.splitlines():
        if line.startswith("| ") and AUDIT_SURFACE_COLUMNS[0] in line:
            header_line = line
            break
    assert header_line, "md にサーフェステーブルヘッダ行が見つからない (LOW-05 違反)"
    for col in AUDIT_SURFACE_COLUMNS:
        assert col in header_line, (
            f"AUDIT_SURFACE_COLUMNS の column {col!r} が md ヘッダ行に無い (LOW-05 違反)"
        )
    # json の surface_map 各 row が AUDIT_SURFACE_COLUMNS の全キーを持つこと
    for i, row in enumerate(SURFACE_ROWS):
        for col in AUDIT_SURFACE_COLUMNS:
            assert col in row, (
                f"SURFACE_ROWS[{i}] に AUDIT_SURFACE_COLUMNS のキー {col!r} が無い (LOW-05 違反)"
            )

    return (md_path, json_path)


__all__ = [
    "AUDIT_SURFACE_COLUMNS",
    "SURFACE_ROWS",
    "SC_CORRESPONDENCE",
    "RECOVERY_CEILING_NOTE",
    "CALIBRATION_BL_INFERIOR_NOTE",
    "ODDS_JODDS_REVERIFICATION_NOTE",
    "KNOWN_LIMITATIONS",
    "generate_audit_report",
    "_format_surface_table_md",
    "_format_sc_correspondence_md",
]


if __name__ == "__main__":
    md, js = generate_audit_report()
    print(f"{md.name} / {js.name}")  # noqa: T201 (CLI 実行確認用)
