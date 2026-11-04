# Host Adapters（宿主适配器）

> 通用 Core（SKILL.md、playbooks/、scripts/prism/）**不出现任何宿主专有工具名**；
> 宿主差异（子 Agent 调用语法、权限映射、能力降级、会话恢复）只放本目录。
> 会话开始时按当前宿主选择**恰好一个** adapter，其余不加载。

## Adapter 契约

每个 `<host>.md` 必须定义以下小节：

| 小节 | 必须回答的问题 |
|---|---|
| **子 Agent 生成** | Worker / Verifier 怎么派生？用什么语法 / 工具 / 进程？ |
| **pack → result 传递** | `packets/worker-<H>.md` 如何交给子 Agent？WorkerResult JSON 如何回传？ |
| **权限映射** | 授权 Gate 的动作组在本宿主对应哪些原生能力 / 审批机制？ |
| **能力降级** | 宿主缺某能力（如无子 Agent、无网络工具）时如何降级？ |
| **会话与恢复** | 会话中断后如何接班？哪些状态在宿主侧、哪些在案件目录？ |
| **实测记录** | 最近一次实测的日期、命令与结果；未实测的明确标注"未实测" |

## 通用规则（所有 adapter 共享）

1. **packets 与 results 走文件，不走对话记忆**：子 Agent 只拿到 pack 文件路径；
   结果写 `results/` 下的 JSON 文件，主 Agent 用 `prism.py schema` 契约校验后入库。
2. **主 Agent 是唯一入库者**：子 Agent 永不直接写 `ledger.jsonl`。
3. **Verifier 必须独立**：Verifier 子 Agent 不得看到 Worker 的推理叙事
   （`verify-pack` 已在装配层排除）；有原生子 Agent 的宿主必须用真子 Agent，
   没有的按 generic 顺序模式由同一 Agent 分阶段扮演并明确声明角色切换。
4. **授权 Gate 在宿主层同样生效**：adapter 的权限映射不得放宽 Core 授权纪律，
   只能收窄。
5. **不虚标**：adapter 只描述已实现 / 已实测的能力；未实测的部分明确标注。

## 注册表

| Adapter | 宿主 | 子 Agent 方式 | 状态 |
|---|---|---|---|
| [generic.md](generic.md) | 任意宿主（无原生子 Agent 假设） | 主 Agent 顺序分阶段扮演 | ✅ 可用（测试覆盖） |
| [omp.md](omp.md) | omp（pi 系 CLI Agent） | 原生 `task` 子 Agent / `-p` 无头进程 | ✅ CLI 已实测；子 Agent 派发未实测（P4） |
| [workbuddy.md](workbuddy.md) | WorkBuddy 桌面 | 原生子 Agent（Agent 工具） | ✅ 已实测（T-021，闭环通过） |
| [dsh.md](dsh.md) | DSH Desktop（dsh-prism 插件） | `prism_spawn` 控制工具 | 📄 文档就绪，实测按设计排期 P4 |

> 新增宿主：复制本契约，新建 `<host>.md`，在本表登记
> 的注册表断言。
