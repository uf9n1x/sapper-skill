# ADR-0004：根 SKILL.md 演进为正式 Skill 入口（P0 安全纠正落点）

- **状态**：已接受（命名部分已被 ADR-0012 取代：最终名 `sapper-skill`）
- **日期**：2026-11-03
- **更新**：2026-11-04 Q8 关闭，最终命名决策见 ADR-0012

## 背景

T-010（P0 安全纠正）要求修正旧 Skill 的反向授权表述（旧 `SKILL.md:20`："超出范围或存在歧义的操作直接做"）。该文件位于 `reference/projects/legacy-pentest-redteam/` 只读快照内（见 ADR-0003），**不可修改**，因此修正必须落在本项目资产上。

存在两个候选落点：

1. P0 即将根 `SKILL.md` 从"项目骨架说明"演进为正式 Skill 入口，写入修正后的授权 Gate
2. P0 只新建 `references/authorization.md` 承载授权纪律，SKILL.md 整体重写推迟到 P1/T-020

## 决策

- 采用方案 1：根 `SKILL.md` 直接演进为正式 Skill 入口
- **name 保持 `prism-skill`**；最终打包目录名与 name 是否改为 `pentest-redteam`，推迟到 P4 多宿主验收时决定（已登记 open-questions Q8）
- frontmatter 遵循通用 Core 规范：`agent_created: true`，**不声明宿主专有 `allowed-tools`**，宿主差异只放 `references/hosts/`（P1 建立）
- 授权 Gate 采用修正版语义：一次声明、战役常驻、按 `动作类别 + 目标范围 + 影响类型` 分组审批、越界与歧义默认不执行
- 授权纪律的机器可读门禁固化在 `tests/test_skill_authorization.py`：反向规则以任何变体回归即测试失败

## 理由

- T-010 验收项"SKILL.md:20 不再出现越界直接做"需要在本仓库内机读可查，方案 2 无法闭环
- 用户已确认（2026-11-03 会话）：根 SKILL.md 直接演进、名称暂保持 prism-skill
- 修正后的授权 Gate 是每次加载都需要的硬规则，属于 SKILL.md 的本职内容；playbooks 与路由精简仍留给 P1，职责不越界

## 后果

- 根 SKILL.md 的角色从"文档管理入口"变为"授权渗透 Skill 入口"，开发状态导航压缩为末节
- description 必须如实标注"P0 基线建设期"（不虚标原则），P1/P2 能力落地后同步更新
- v1 最小命令面（`scripts/case_ledger.py`）随 SKILL.md 一起生效，其行为由 77 项回归测试锁定
- 未来若在 P4 决定改名为 `pentest-redteam`，需同步修改 frontmatter、目录与打包配置，并重跑触发评测
