"""Phase 5 backtest フル行列 report 生成（BACK-04 / §11.2 / RESEARCH §10）.

Plan 05-05 で ``scripts/run_backtest.py`` が消費する report 出力層。全25候補
(5 BT窓 × 2 policy × 2 model + 5 BL-3) の backtest 結果を一括報告する。

**設計の核心（BACK-04 / RESEARCH §10.2 / Plan 05-05 must_haves）:**

1. **winner 強調禁止（BACK-04・§11.2・T-05-15 mitigate）**: highest-recovery の backtest_id を
   「推奨」「採用候補」として突出させる記述は一切生成しない。全候補を ``backtest_id`` 辞書順で
   並べ・一括提示するのみ。主モデルの確定は Phase 6 D-03/D-04 事前登録基準に委ねる
   （後知恵排除・Information Disclosure）。
2. **§11.2 odds policy 固定履行確認セクション**: 事前登録 policy
   (``30min_before`` / ``10min_before``) が履行されたこと・レース後のオッズ差し替え・
   最終オッズ無条件使用がないことを明示する専用セクションを設ける。
3. **report columns 契約（LOW-05・T-05-LOW mitigate）**: ``REPORT_COLUMNS`` 定数で
   列定義を外部化し・report.md の列ヘッダと report.json の comparison_table キーが
   1:1 になることをテストで検証する（grep 否定でなく presence assert）。
4. **BL-3 §14.2 caveat**: notes に ``BL3_BETTING_CAVEAT`` 由来の注記を含める。
5. **実JODDS状況明記**: reports に合成データ版/取得完了版のどちらかを明示する。

参照: 05-05-PLAN.md Task 1 / 05-RESEARCH.md §10 / src/model/evaluator.py (report パターン) /
      src/ev/bl3_betting.py (BL3_BETTING_CAVEAT).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model.artifact import _atomic_write_text
from src.ev.bl3_betting import BL3_BETTING_CAVEAT

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# report の列契約（LOW-05: report.md 列ヘッダ・report.json comparison_table キーと 1:1）
# run_backtest.py が全 backtest 行（dict）にこれらのキーを埋める。
REPORT_COLUMNS: tuple[str, ...] = (
    "backtest_id",
    "bt_name",
    "odds_policy",
    "model_type",
    "recovery_rate",
    "P/L",
    "max_DD",
    "selected",
    "effective_bet",
    "refund",
    "hit_rate",
)

# report の section title（BACK-04・§11.2）
REPORT_TITLE: str = "Phase 5 Backtest Report"

# §11.2 odds policy 固定履行確認（T-05-15/BACK-04）
ODDS_POLICY_FIXED_NOTE: str = (
    "§11.2 odds policy 固定履行: 全 backtest 行の odds_snapshot_policy は事前登録値 "
    "(30min_before / 10min_before / confirmed) のいずれかであり・レース後の有利オッズ選択・"
    "最終オッズ無条件使用・欠損時の都合の良い時点への差し替えは一切行われていない。"
    "BACK-04 / §11.2 構造的ブロック (T-05-15 mitigate)。"
)

# BACK-04 後知恵排除注記（winner 単独報告禁止）
NO_WINNER_OVERRIDE_NOTE: str = (
    "BACK-04: 本報告は全候補を backtest_id 辞書順で一括提示する。回収率が最も高い backtest_id を"
    "「推奨」「採用候補」と突出させる記述は一切ない。主モデル確定は Phase 6 D-03/D-04 の事前登録"
    "選定基準 (Calibration 重視) に委ねる (後知恵排除・Information Disclosure)。"
)

# 主モデル確定 Phase 6 委任注記
PHASE6_SELECTION_NOTE: str = (
    "主モデルの最終確定は Phase 6 D-03/D-04 の事前登録選定基準 (Calibration 重視: "
    "calibration_max_dev + sum(p) 適合度を主要・brier/logloss 次点・auc 参考) で行う。"
    "本 Phase 5 report は素材提供のみ。"
)

# 馬単位 JOIN / category map 注記（HIGH-1/HIGH-2/HIGH-5 検証済メモ）
HORSE_LEVEL_JOIN_NOTE: str = (
    "HIGH-1/HIGH-2: 予測・オッズ snapshot・label の JOIN は全て (race_key, umaban) 単位で実行し・"
    "merge 後に行数が入力予測行数と一致することを assert している (cartesian duplication 構造的ブロック)。"
    "HARAI は race-level slot レコードのため例外的に on=['race_key'] + validate='many_to_one' で馬行に"
    "ブロードキャストし・行ベース slot lookup (_lookup_payfukusyo_pay) で払戻を確定する (HIGH-C cycle-2)。"
)
BT_CATEGORY_MAP_REFIT_NOTE: str = (
    "HIGH-5: 各 BT窓 train 期間のみで fit_category_map を呼出し・test 窓の未観測 ID を __UNSEEN__ "
    "sentinel に mapping している (全期間固定 category_map の再利用回避・test 窓 ID 漏洩防止)。"
)


def _format_float(v: Any) -> str:
    """float を report 用文字列に整形（NaN は 'nan'・それ以外は小数4桁）。"""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "nan"
    import math

    if math.isnan(fv):
        return "nan"
    return f"{fv:.4f}"


def _format_comparison_table_md(rows: list[dict[str, Any]]) -> str:
    """comparison_table (list of dict) を markdown 表に変換する。

    列は REPORT_COLUMNS 順に固定。``run_train_predict.py:516-523`` の手動マークダウン表パターン
    (tabulate 非依存・evaluator._df_to_markdown_table と同一方針)。
    """
    header = "| " + " | ".join(REPORT_COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in REPORT_COLUMNS) + " |"
    body_lines: list[str] = []
    for row in rows:
        cells: list[str] = []
        for col in REPORT_COLUMNS:
            v = row.get(col)
            if col in {"recovery_rate", "hit_rate"}:
                cells.append(_format_float(v))
            elif col in {"P/L", "max_DD"}:
                # int 系
                try:
                    cells.append(str(int(v)))
                except (TypeError, ValueError):
                    cells.append("nan")
            elif col in {"selected", "effective_bet", "refund"}:
                try:
                    cells.append(str(int(v)))
                except (TypeError, ValueError):
                    cells.append("0")
            else:
                cells.append(str(v) if v is not None else "")
        body_lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + body_lines)


def _format_notes(jodds_status: str) -> list[str]:
    """notes リストを構築する。

    Parameters
    ----------
    jodds_status : str
        実JODDS取得状況を示す文字列。``'synthetic'`` (合成データ) / ``'partial'`` (一部取得) /
        ``'complete'`` (取得完了) のいずれか。run_backtest.py 側で判定して渡す。
    """
    if jodds_status == "synthetic":
        jodds_note = (
            "実JODDS状況: 合成データ版 (run_backtest --synthetic)。実JODDS取得は進行中のため・"
            "本 report の数値は pipeline 動作検証用であり投資判断の素材ではない。"
            "実データ版は後続 Plan 05-06 checkpoint で生成予定。"
        )
    elif jodds_status == "partial":
        jodds_note = (
            "実JODDS状況: 部分取得 (coverage gate が閾値未満の可能性あり・report の coverage "
            "サマリを参照)。全 BT窓 × policy で horse-level usable-odds coverage >= 閾値になるまで"
            "本 report の数値は確定的でない。"
        )
    else:  # complete
        jodds_note = (
            "実JODDS状況: 取得完了 (全 BT窓 × policy で horse-level usable-odds coverage >= 閾値)。"
            "本 report の数値は Phase 6 主モデル確定に向けた素材として参照可能。"
        )

    return [
        NO_WINNER_OVERRIDE_NOTE,
        ODDS_POLICY_FIXED_NOTE,
        f"BL-3 §14.2 caveat: {BL3_BETTING_CAVEAT}",
        PHASE6_SELECTION_NOTE,
        HORSE_LEVEL_JOIN_NOTE,
        BT_CATEGORY_MAP_REFIT_NOTE,
        jodds_note,
    ]


def generate_report(
    all_backtests: list[dict[str, Any]],
    *,
    output_dir: str | Path = "reports",
    jodds_status: str = "synthetic",
    coverage_summary: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    """全 backtest 結果を reports/05-backtest.{md,json} に一括報告する (BACK-04)。

    Parameters
    ----------
    all_backtests : list[dict]
        各 backtest の metrics dict リスト (run_backtest.py が構築)。
        各 dict は REPORT_COLUMNS の全キーを含むこと。
    output_dir : str | Path
        出力ディレクトリ (既定 ``'reports'``)。
    jodds_status : str
        実JODDS取得状況 (``'synthetic'`` / ``'partial'`` / ``'complete'``)。
    coverage_summary : list[dict] | None
        BT窓 × policy 毎の horse-level/race-level coverage サマリ (MEDIUM-B cycle-2)。
        None の場合は coverage サマリセクションを省略。

    Returns
    -------
    tuple[Path, Path]
        ``(md_path, json_path)``。

    Notes
    -----
    - **BACK-04 (winner 単独報告禁止)**: 本関数は highest-recovery の backtest_id を突出
      させる語句を出力しない。全候補を backtest_id 辞書順で並べるのみ。
    - sort は backtest_id の昇順 (辞書順・決定論的・seed 非依存)。
    """
    out_dir = Path(output_dir)
    md_path = out_dir / "05-backtest.md"
    json_path = out_dir / "05-backtest.json"

    # BACK-04: backtest_id 辞書順 (決定論的・winner 強調禁止)
    sorted_rows = sorted(all_backtests, key=lambda r: str(r.get("backtest_id", "")))

    # --- Markdown ---
    md_lines: list[str] = []
    md_lines.append(f"# {REPORT_TITLE} (BACK-01..04 / §15.5 / §19.1)\n")
    md_lines.append("\n")
    md_lines.append("## 比較表 (全候補一括提示・winner 強調なし・BACK-04)\n")
    md_lines.append("\n")
    md_lines.append(_format_comparison_table_md(sorted_rows))
    md_lines.append("\n\n")

    md_lines.append("## §11.2 odds policy 固定履行確認\n")
    md_lines.append("\n")
    md_lines.append(f"- {ODDS_POLICY_FIXED_NOTE}\n")
    md_lines.append(
        f"- 事前登録 policy 一覧: 30min_before / 10min_before (主モデル 20 backtest)・"
        "confirmed (BL-3 5 backtest・JODDS 時点非依存 sentinel)\n"
    )
    md_lines.append(
        "- backtest_strategy_version (全 backtest 行共通): fukusho_ev_v1 (§19.1 再現性 stamp)\n"
    )
    md_lines.append("\n")

    if coverage_summary:
        md_lines.append("## MEDIUM-B JODDS coverage サマリ (horse-level usable-odds)\n")
        md_lines.append("\n")
        md_lines.append(_format_coverage_table_md(coverage_summary))
        md_lines.append("\n\n")

    md_lines.append("## 注記\n")
    md_lines.append("\n")
    for note in _format_notes(jodds_status):
        md_lines.append(f"- {note}\n")
    md_payload = "".join(md_lines)
    _atomic_write_text(md_path, md_payload)

    # --- JSON (sort_keys=True で byte-reproducible・evaluator.py パターン) ---
    json_payload = json.dumps(
        {
            "comparison_table": sorted_rows,
            "metrics": {
                str(r.get("backtest_id", "")): r for r in sorted_rows
            },
            "constants": {
                "REPORT_COLUMNS": list(REPORT_COLUMNS),
                "FUKUSHO_EV_V1_STRATEGY": "fukusho_ev_v1",
                "ODDS_SNAPSHOT_POLICIES": {
                    "30min_before": 30,
                    "10min_before": 10,
                },
            },
            "coverage_summary": coverage_summary or [],
            "notes": _format_notes(jodds_status),
            "jodds_status": jodds_status,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    _atomic_write_text(json_path, json_payload)

    return (md_path, json_path)


def _format_coverage_table_md(coverage_summary: list[dict[str, Any]]) -> str:
    """coverage サマリ (BT窓 × policy) を markdown 表にする。"""
    cols = ("bt_name", "policy", "horse_level_coverage", "race_level_coverage", "threshold", "status")
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    body: list[str] = []
    for row in coverage_summary:
        cells = []
        for c in cols:
            v = row.get(c)
            if c in {"horse_level_coverage", "race_level_coverage", "threshold"}:
                cells.append(_format_float(v))
            else:
                cells.append(str(v) if v is not None else "")
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + body)


__all__ = [
    "REPORT_COLUMNS",
    "REPORT_TITLE",
    "ODDS_POLICY_FIXED_NOTE",
    "NO_WINNER_OVERRIDE_NOTE",
    "PHASE6_SELECTION_NOTE",
    "HORSE_LEVEL_JOIN_NOTE",
    "BT_CATEGORY_MAP_REFIT_NOTE",
    "generate_report",
    "_format_comparison_table_md",
    "_format_notes",
    "_format_coverage_table_md",
]
