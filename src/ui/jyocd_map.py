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

# repo root 相対・Streamlit は repo root から ``streamlit run`` する前提（UI-SPEC・D-01）
_CODE_TABLES_PATH = Path("src/config/code_tables.yaml")


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
