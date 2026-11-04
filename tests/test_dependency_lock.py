"""锁定依赖冒烟测试（T-011）。

验证两件事：
1. requirements.lock 声明的全部主依赖可导入且 API 口径符合设计预期
2. 当前环境安装的版本与 requirements.lock 逐项一致（lock 可复现性）

锁定文件本身禁止手工编辑：变更依赖必须走 ADR 并重新 `uv pip compile`。
"""

from __future__ import annotations

import importlib
from importlib.metadata import version as installed_version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_LOCK = PROJECT_ROOT / "scripts" / "requirements.lock"

# dist 名 → 导入模块名（二者不一致的依赖显式映射）
DIST_TO_MODULE = {
    "pydantic": "pydantic",
    "typer": "typer",
    "rich": "rich",
    "pyyaml": "yaml",
    "filelock": "filelock",
    "rank-bm25": "rank_bm25",
    "jieba": "jieba",
    "rapidfuzz": "rapidfuzz",
    "networkx": "networkx",
    "jinja2": "jinja2",
    "pyvis": "pyvis",
    "python-frontmatter": "frontmatter",
}
DECLARED_MAIN_DEPS = set(DIST_TO_MODULE)


def _lock_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in REQUIREMENTS_LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, pinned = line.partition("==")
        pins[name.strip().lower()] = pinned.strip()
    return pins


def test_requirements_lock_exists_and_covers_main_deps():
    pins = _lock_pins()
    missing = DECLARED_MAIN_DEPS - set(pins)
    assert not missing, f"requirements.lock 缺少主依赖：{missing}"


def test_all_main_dependencies_importable():
    for module in DIST_TO_MODULE.values():
        importlib.import_module(module)  # ImportError 即失败


def test_installed_versions_match_lock():
    pins = _lock_pins()
    mismatches = []
    for dist in DECLARED_MAIN_DEPS:
        actual = installed_version(dist)
        expected = pins[dist]
        if actual != expected:
            mismatches.append(f"{dist}: installed {actual} != lock {expected}")
    assert not mismatches, "环境与 lock 不一致：\n" + "\n".join(mismatches)


def test_pydantic_v2_api_available():
    import pydantic

    class Sample(pydantic.BaseModel):
        x: int

    assert Sample(x=1).model_dump() == {"x": 1}
    assert hasattr(pydantic, "TypeAdapter")


def test_networkx_directed_multigraph_available():
    import networkx as nx

    graph = nx.MultiDiGraph()
    graph.add_edge("asset", "service", relation="runs_on")
    assert graph.has_edge("asset", "service")


def test_rapidfuzz_fuzzy_ratio_available():
    from rapidfuzz import fuzz

    assert fuzz.ratio("prism", "prism") == 100.0
    assert fuzz.ratio("prism", "prims") >= 75.0
