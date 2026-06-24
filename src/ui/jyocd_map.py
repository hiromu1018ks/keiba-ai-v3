"""Phase 7 jyocd→競馬場名マッピング読込 helper（DRY・code_tables.yaml が単一ソース）。

UI 側に jyocd→競馬場名の dict をハードコードしない（D-04 DRY・UI-SPEC）。
``src/config/code_tables.yaml`` の ``jyocd`` セクション（01-10 = JRA 東西10場・実データ
SELECT DISTINCT で裏取り）を PyYAML ``safe_load`` で読込・返す。

参照: 07-01-PLAN.md must_haves / 07-PATTERNS.md §src/ui/jyocd_map.py /
      src/config/code_tables.yaml (L9-21・入力データ)
"""

from __future__ import annotations

from pathlib import Path

import yaml

# CR-02 (deep review Critical): cwd 相対でなく __file__ ベースの絶対パスで解決。
# scripts/run_export_predictions_csv.py が load_predictions → load_jyocd_map を呼ぶため・
# repo root 以外の cwd (cron / CI / 別 worktree / --output 指定) から CLI を実行すると
# FileNotFoundError で OUT-01 出力が落ちないよう・モジュール位置から絶対解決する。
# src/ui/jyocd_map.py → parents[2] = repo root。
_CODE_TABLES_PATH = Path(__file__).resolve().parents[2] / "src" / "config" / "code_tables.yaml"


def load_jyocd_map() -> dict[str, str]:
    """``src/config/code_tables.yaml`` から jyocd→競馬場名マッピングを読込む。

    Returns
    -------
    dict[str, str]
        jyocd コード（"01".."10"・JRA 東西10場）→ 競馬場名（"札幌".."小倉"）の mapping。
        ``code_tables.yaml`` の ``jyocd`` セクションを ``dict()`` で返す。

    Examples
    --------
    >>> m = load_jyocd_map()
    >>> m["01"], m["10"]
    ('札幌', '小倉')
    """
    data = yaml.safe_load(_CODE_TABLES_PATH.read_text(encoding="utf-8"))
    return dict(data["jyocd"])


__all__ = ["load_jyocd_map"]
