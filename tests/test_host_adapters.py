"""Host adapter 契约测试（T-021，ADR-0006）。

锁定三条纪律：
1. 注册表完整：references/hosts/README.md 登记全部 adapter
2. 契约小节：每个 adapter 必须定义六节（含实测记录）
3. Core 纯净：SKILL/playbooks/prism 源码不出现宿主专有名称
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import PROJECT_ROOT, run_prism

HOSTS_DIR = PROJECT_ROOT / "references" / "hosts"
README = HOSTS_DIR / "README.md"

# 契约要求的必备小节（ADR-0006）
REQUIRED_SECTIONS = [
    "子 Agent 生成",
    "result 传递",  # “pack → result 传递”的稳定子串
    "权限映射",
    "能力降级",
    "会话与恢复",
    "实测记录",
]

# Core 文件中禁止出现的宿主专有名称（词边界、大小写不敏感）
FORBIDDEN_CORE_PATTERNS = [
    r"\bomp\b",
    r"\bdsh\b",
    r"\bworkbuddy\b",
    r"\bcodex\b",
    r"\bdeepseek\b",
]


def core_files() -> list[Path]:
    files = [PROJECT_ROOT / "SKILL.md"]
    files += sorted((PROJECT_ROOT / "playbooks").glob("*.md"))
    files.append(PROJECT_ROOT / "scripts" / "prism.py")
    files += sorted((PROJECT_ROOT / "scripts" / "prism").glob("*.py"))
    files.append(PROJECT_ROOT / "scripts" / "case_ledger.py")
    return files


class TestRegistry:
    def test_readme_exists_with_contract(self):
        assert README.is_file()
        content = README.read_text(encoding="utf-8")
        assert "Adapter 契约" in content
        assert "注册表" in content

    def test_registry_lists_all_adapters(self):
        adapters = {p.stem for p in HOSTS_DIR.glob("*.md") if p.stem != "README"}
        content = README.read_text(encoding="utf-8")
        for name in adapters:
            assert f"{name}.md" in content, f"registry missing {name}.md"

    def test_hosts_command_lists_adapters(self):
        result = run_prism("hosts")
        assert result.returncode == 0, result.stderr
        listed = set(result.stdout.split())
        adapters = {p.stem for p in HOSTS_DIR.glob("*.md") if p.stem != "README"}
        assert listed == adapters


class TestAdapterContract:
    def test_every_adapter_defines_required_sections(self):
        for path in sorted(HOSTS_DIR.glob("*.md")):
            if path.stem == "README":
                continue
            content = path.read_text(encoding="utf-8")
            for section in REQUIRED_SECTIONS:
                assert section in content, f"{path.name} missing section: {section}"

    def test_field_test_record_is_honest(self):
        """实测记录必须给出日期，或明确标注“未实测”；禁止含糊其辞。"""
        for path in sorted(HOSTS_DIR.glob("*.md")):
            if path.stem == "README":
                continue
            content = path.read_text(encoding="utf-8")
            match = re.search(r"## 实测记录\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
            assert match, f"{path.name} 实测记录小节为空"
            body = match.group(1)
            has_date = re.search(r"20\d{2}-\d{2}-\d{2}", body)
            assert has_date or "未实测" in body, (
                f"{path.name} 实测记录既无日期也未标注未实测"
            )

    def test_generic_is_documented_fallback(self):
        content = (HOSTS_DIR / "generic.md").read_text(encoding="utf-8")
        assert "顺序" in content
        assert "sequential" in content  # 报告标注要求


class TestCorePurity:
    def test_core_files_contain_no_host_specific_names(self):
        violations: list[str] = []
        for path in core_files():
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_CORE_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    violations.append(f"{path.name}: /{pattern}/")
        assert not violations, f"host-specific names leaked into core: {violations}"

    def test_skill_routes_to_hosts_dir(self):
        skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "references/hosts/" in skill
