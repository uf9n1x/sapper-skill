# ADR-0012 Skill 最终命名：sapper-skill

- 状态：已接受（2026-11-04）
- 关联：ADR-0004（P0 命名暂定）、open-questions Q8（本 ADR 关闭）

## 背景

ADR-0004 决定 P0 期暂保持 `prism-skill`，最终打包目录名与 frontmatter `name` 推迟到 P4 决定（Q8）。升级方案 §14 曾建议改回 `pentest-redteam` 以便直接替换旧 Skill。

## 决策

用户决策（2026-11-04）：**Skill 最终命名为 `sapper-skill`，以此为准。**

- frontmatter `name: sapper-skill`；最终打包目录名 `sapper-skill/`（目录名与 name 一致）
- **不**改回 `pentest-redteam`：本项目定位为新独立 Skill，不承担原地替换旧 Skill 的职责
- 开发仓库目录（OS 路径 `prism-skill/`）暂不重命名，避免中断进行中的会话与本地工具链；P4 打包产物使用 `sapper-skill/`
- 内部 Python 包 `scripts/prism/` 与入口 `scripts/prism.py` 保持不变（实现代号，非 Skill 名）

## 影响

- 授权纪律测试 `tests/test_skill_authorization.py` 的 name 断言同步更新
- 文档面（README / SKILL.md / docs / project-state.yml / NEW_SESSION_PROMPT.md）同步改名
- `reference/` 快照（含 legacy-pentest-redteam）不涉及，继续只读
