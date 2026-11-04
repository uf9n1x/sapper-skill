"""P0 安全纠正的机器可读门禁（T-010）。

锁定根 SKILL.md 的授权纪律，防止旧版反向规则（"超出范围或存在歧义的操作
直接做"）以任何变体回归。这是 T-010 验收项"SKILL.md:20 不再出现'越界
直接做'"的自动化形态。
"""

from __future__ import annotations

import re

from conftest import SKILL_MD

# 旧版反向授权规则的原文与核心变体，一律禁止出现。
REVERSED_RULE_PATTERNS = [
    "超出范围或存在歧义的操作直接做",
    "默认先做",
    "仅在授权文档明确禁止时才不做",
    "超出范围.*直接(执行|做)",
]


class TestNoReversedAuthorizationRule:
    def test_reversed_rule_text_absent(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        for pattern in REVERSED_RULE_PATTERNS:
            assert not re.search(pattern, content), f"反向授权规则回归：{pattern}"

    def test_scope_gate_defaults_to_deny(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        assert "越界" in content
        assert re.search(r"默认不执行|不执行该动作|停止该动作", content), (
            "缺少『越界/歧义默认不执行』的显式表述"
        )


class TestCorrectedAuthorizationGate:
    def test_one_time_declaration_and_campaign_residency(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        assert "一次声明" in content
        assert "战役常驻" in content or "常驻" in content

    def test_high_impact_approval_grouping(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        assert "高影响" in content
        for term in ("动作类别", "目标范围", "影响类型"):
            assert term in content, f"缺少审批分组要素：{term}"
        assert re.search(r"只确认一次|只询问一次|不重复(确认|询问)", content)

    def test_untrusted_target_content_rule(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        assert re.search(r"不可信", content), "缺少『目标输出/文档不可信』纪律"

    def test_soft_boundary_disclaimer(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        assert "软约束" in content, "缺少『scope-check 是流程软约束』声明"


class TestFrontmatter:
    def test_name_and_agent_created(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        match = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
        assert match and match.group(1) == "sapper-skill"
        assert re.search(r"^agent_created:\s*true\s*$", content, re.MULTILINE)

    def test_no_host_specific_allowed_tools(self):
        """通用 Core 不声明宿主专有 allowed-tools（宿主差异只放 host adapter）。"""
        content = SKILL_MD.read_text(encoding="utf-8")
        assert not re.search(r"^allowed-tools:", content, re.MULTILINE)

    def test_description_is_precise_and_authorized_scope_only(self):
        content = SKILL_MD.read_text(encoding="utf-8")
        match = re.search(
            r"^description:\s*\"(.*)\"", content, re.MULTILINE | re.DOTALL
        )
        assert match, "缺少 description"
        description = match.group(1)
        assert "授权" in description
        assert re.search(r"渗透测试|红队|攻防演练|漏洞验证", description)
        # 不虚标：description 必须如实标注当前开发状态（开发中/基线/建设/评测期）
        assert re.search(r"开发中|基线|建设|评测", description), (
            "description 未如实标注当前开发状态（不虚标原则）"
        )
