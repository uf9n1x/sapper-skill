# sapper-skill — 假设驱动的授权渗透测试 Skill

> ⚠️ **仅限获得明确授权的安全测试、红队评估、CTF 与漏洞赏金。**
> 使用者须自行确认对目标拥有授权；未授权目标与黑灰产不在适用范围，作者不对未授权使用承担责任。

面向任意 Agent 宿主（DSH / omp / WorkBuddy 等）的渗透测试 Skill：**指挥官只决策、工兵只执行、复核者只验证**，三者围绕一个**可证伪的假设账本**协同推进。Python 确定性控制面负责状态、证据与门禁——Agent 层只产出叙事，账本是唯一真相源。纯本机执行，不依赖 Docker / 常驻服务；面板产物离线单文件打开，也可一键启动实时服务。

## 特性

- **授权 Gate**：一次声明覆盖整个战役，动作组申报与审批入账（`approval` 记录）；越界动作默认不执行，扫描器告警强制 `requires_verification`，不得直接成为确认。
- **角色结构性隔离**：`pack` / `verify-pack` 渐进披露——工兵包不含无关目标，复核包刻意排除工兵叙事；confirmed 裁决必须由独立 Verifier 结果驱动。
- **v2 事件账本**：`ledger.jsonl` 唯一真相源，追加式事件（fact / intent / run / approval / hypothesis / evidence / verdict），确定性回放，v1 旧账本 `migrate` 一键升级。
- **崩溃可恢复**：claim / lease 租约 + 幂等 ingest（同键重放账本逐字节不变）+ 半行尾修复（`repair`）+ 过期租约恢复（`recover`）。
- **工具输出消化**：nmap / masscan / httpx / nuclei / 通用 JSON 五类 parser，秘密脱敏，多来源资产 identity 归一化合并（模糊相似进人工审查队列，不静默合并）。
- **可解释召回与经验沉淀**：BM25 + 模糊 + 结构化 + 一跳图扩展的混合召回，逐项权重可解释；KB 条目带信任级别与过期警告，晋升有 confirmed + 去目标化硬门禁。
- **离线可视化面板**：dashboard / attack-graph / board / mermaid 四产物单文件离线打开（无 CDN），`serve` 一键升级为实时面板（账本变化自动重渲染，可随时暂停/恢复），中英双语切换。
- **报告门禁**：`prism.py verify` 强制 confirmed 三角色闭环（observation / reproduction / impact）且带 `verifier_run` 溯源，不通过不出报告。

## 安装

```bash
git clone https://github.com/uf9n1x/sapper-skill.git
cd sapper-skill
python -m venv .venv
.venv/Scripts/pip install -r scripts/requirements.lock   # Windows
# Linux/macOS: .venv/bin/pip install -r scripts/requirements.lock
```

把仓库目录注册为你宿主的 Skill（按宿主的 Skill/扩展装载方式），或在任意会话中直接引用 `SKILL.md` 作为角色指令。

**验证**：

```bash
python -X utf8 scripts/prism.py hosts        # 列出可用宿主 adapter
python -X utf8 scripts/prism.py schema --format markdown
```

**依赖**：Python 3.10+，其余见 `scripts/requirements.lock`（uv pip compile 生成，禁止手改）。

## 快速上手

1. **声明授权**：对 Agent 说明目标与范围（一次声明，战役常驻）；
2. **立假设、派工兵**：指挥官把目标拆成可证伪假设（`hypothesis`），`pack` 生成最小上下文包派发给工兵；
3. **入库与复核**：工兵写结果 JSON（SHA-256 锚定工件），`ingest` 幂等入库；`verify-pack` 派发独立复核，confirmed 必须由复核结果驱动；
4. **出报告**：`python -X utf8 scripts/prism.py verify <case>` 门禁通过后按 `playbooks/report.md` 输出；
5. **看面板**：`python -X utf8 scripts/prism.py render <case>` 离线四产物，或 `serve <case>` 启动实时面板（默认 `http://127.0.0.1:8765`）。

入口协议、角色边界与全部命令见 [SKILL.md](SKILL.md)。

## 架构速览

```
Agent 宿主（Commander / Worker / Verifier 角色）
        │  读写
        ▼
case/  ledger.jsonl（唯一真相源）+ artifacts/（SHA-256 锚定）+ results/（结果包）
        │
        ▼
scripts/prism/  确定性控制面
```

| 模块 | 职责 |
|---|---|
| `models.py` | 冻结协议：WorkerResult 契约 + 七类账本记录（pydantic 校验） |
| `state.py` | 确定性回放：引用完整性、Intent/Run 状态派生、findings 投影 |
| `migration.py` | v1 → v2 迁移 + 回放等价性校验 |
| `ingest.py` | 幂等入库：结果包校验 → 记录追加 → run 完成 |
| `packets.py` | `pack` / `verify-pack` 角色上下包装配（最小上下文） |
| `parsers.py` + `identity.py` | 工具输出消化、秘密脱敏、资产 identity 归一化 |
| `recall.py` + `knowledge.py` | 混合召回与 KB 晋升门禁 |
| `render.py` + `live.py` | 离线四产物渲染与实时面板服务 |
| `cli.py` | `prism.py` 命令面（18 命令） |

宿主差异（子 Agent 生成语法、权限映射、降级路径）见 `references/hosts/`——按宿主选择恰好一个 adapter，无匹配时退回 `generic.md` 顺序模式。

## 文档

| 文档 | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | Skill 入口：授权 Gate、角色协议、证据纪律、全部命令 |
| [playbooks/](playbooks/) | 五阶段角色手册：reason / explore / verify / report / focused |
| [references/hosts/](references/hosts/) | 宿主适配契约（DSH / omp / WorkBuddy / generic） |
| [references/result-schema.md](references/result-schema.md) | Worker 结果包 JSON 契约（字段级文档） |
| [kb/README.md](kb/README.md) | 经验知识库格式与晋升门禁 |

## 参考项目

- [nvwabase · 女娲基座](https://github.com/N1nEmAn/nvwabase) —— 事实—意图图机制的灵感来源。
- [sapper-v2](https://github.com/N1nEmAn/sapper-v2) —— 多 Agent 渗透协作的编排思路参照。
- [dsh-pentest](https://github.com/howmp/dsh-pentest) —— 同类 DSH bundle 的包结构参照。
- [dsh-prism](https://github.com/uf9n1x/dsh-prism) —— 同一编排思想在 DSH 插件形态的落地。

## License

[MIT](LICENSE)
