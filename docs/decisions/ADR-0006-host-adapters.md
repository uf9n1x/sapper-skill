# ADR-0006: Host Adapter 契约与首批宿主

- **状态**：Accepted
- **日期**：2026-11-03
- **关联**：T-021（P1 Host Adapter 首版）；升级方案 §14（通用 SKILL 不声明宿主
  allowed-tools，宿主差异只放 references/hosts/）；interfaces.md §6（兼容性）

## 背景

P1 Walking Skeleton（T-020）打通了宿主无关的单目标闭环。T-021 要求：
generic 顺序模式可用、至少一个宿主原生子 Agent 模式可用、核心流程无宿主
专有工具名。用户确认首批宿主目标为 **dsh（DSH Desktop）、omp、workbuddy**
（三者在开发机上均可用），并授权自由启动实测。

## 决策

1. **Adapter 契约**：每个宿主一个 `references/hosts/<host>.md`，必须定义六节：
   子 Agent 生成、pack→result 传递、权限映射、能力降级、会话与恢复、实测记录；
   测试（`tests/test_host_adapters.py`）强制检查契约小节与注册表完整性。
2. **传递协议**：packets 与 results 一律走文件（packet 进、JSON result 出），
   不走对话记忆；主 Agent 是唯一入库者——该协议与宿主无关，adapter 只描述
   "如何在本宿主派生与回传"。
3. **首批宿主与状态**：
   - `generic`：顺序模式，主 Agent 分阶段扮演角色，confirmed 标注
     `verification_mode: sequential`；作为一切宿主的降级兜底。
   - `omp`：无头 `-p` 模式已实测（v18.15.0，PowerShell）；`task` 原生子 Agent
     派发闭环留待 P4 实施时验证。
   - `workbuddy`：原生子 Agent 已实测（T-021：Worker + 独立 Verifier 闭环、
     哈希独立比对、门禁先拒后放）。
   - `dsh`：文档基于 dsh-prism 源码与预设先行就绪；实测按设计排期 P4。
4. **纯净性机读**：SKILL.md、playbooks/、scripts/prism/ 禁止出现宿主专有
   名称（omp / dsh / workbuddy / codex 等），由测试强制；SKILL 只路由到
   `references/hosts/`，会话开始时按当前宿主选择恰好一个 adapter。

## 后果

- 新宿主接入成本 = 一个契约文档 + 注册表登记 + 纯净性测试不变。
- 顺序模式的独立性弱于真子 Agent，用 `sequential` 标注补偿（报告透明）。
- dsh 实测推迟到 P4 与"多宿主验收"合并，避免在本阶段引入对 DSH 宿主
  插件机制的逆向依赖。
