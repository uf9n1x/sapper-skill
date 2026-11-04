"""协议文档漂移守卫（T-020）。

references/result-schema.json 与 result-schema.md 由 scripts/prism/models.py
生成并提交入库。本测试强制文档与模型同步：修改模型后必须重新生成文档
（python -X utf8 scripts/prism.py schema --format ... --out ...），
防止"模型 / 文档 / Schema"三处漂移（升级方案 §14）。
"""

from __future__ import annotations

import json

from conftest import PROJECT_ROOT
from prism import models

SCHEMA_JSON = PROJECT_ROOT / "references" / "result-schema.json"
SCHEMA_MD = PROJECT_ROOT / "references" / "result-schema.md"


def test_committed_json_schema_matches_model():
    committed = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    assert committed == models.export_json_schema(), (
        "references/result-schema.json 与模型漂移：请重新生成 "
        "（prism.py schema --format json --out references/result-schema.json）"
    )


def test_committed_markdown_matches_model():
    committed = SCHEMA_MD.read_text(encoding="utf-8")
    assert committed == models.export_markdown(), (
        "references/result-schema.md 与模型漂移：请重新生成 "
        "（prism.py schema --format markdown --out references/result-schema.md）"
    )
