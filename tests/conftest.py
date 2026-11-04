"""sapper-skill 测试共享夹具。

被测对象：
- scripts/case_ledger.py（v1 冻结基线）
- scripts/prism.py + scripts/prism/（P1 起的 v2 控制面骨架）
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
LEDGER_SCRIPT = SCRIPTS_DIR / "case_ledger.py"
PRISM_SCRIPT = SCRIPTS_DIR / "prism.py"
SKILL_MD = PROJECT_ROOT / "SKILL.md"
FIXTURE_V1_CASE = PROJECT_ROOT / "tests" / "fixtures" / "v1" / "case"

# 使 prism 包与 case_ledger 可直接 import（与 `python scripts/prism.py`
# 运行时的 sys.path 语义一致）
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(scope="session")
def ledger_module():
    """以模块方式加载 v1 账本，供单元级回归测试使用。"""
    spec = importlib.util.spec_from_file_location("case_ledger_v1", LEDGER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """以子进程运行 v1 账本 CLI（强制 UTF-8 模式）。"""
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(LEDGER_SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
        check=False,
    )


def run_prism(*args: str) -> subprocess.CompletedProcess[str]:
    """以子进程运行 v2 控制面 CLI（prism.py，强制 UTF-8 模式）。"""
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(PRISM_SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
        check=False,
    )


@pytest.fixture()
def case_dir(tmp_path: Path) -> Path:
    """已初始化的空案件目录。"""
    case = tmp_path / "case"
    case.mkdir()
    (case / "artifacts").mkdir()
    (case / "ledger.jsonl").touch()
    return case


def make_artifact(case: Path, name: str, content: str) -> str:
    """在案件 artifacts/ 下写入证据文件，返回相对路径（POSIX 风格）。"""
    target = case / "artifacts" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"artifacts/{name}"
