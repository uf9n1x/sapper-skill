# T-050 实战评测报告（DVWA 对比基线）

- 日期：2026-11-04
- 协议：`docs/eval/T-050-protocol.md`（同操作者、同工具、同探测目录、预算 ≤40 请求）
- 靶场：DVWA low @ http://192.168.8.159:8080（用户授权，ssh bob → docker `dvwa`）
- 数据：`workspace/t050/{baseline,v2}/`（本地保留，不入 git；cookie 类凭据未落盘）

## 1. 结果总览

| 指标 | 基线（旧版纪律） | v2（sapper-skill） | 阈值 | 结论 |
|---|---|---|---|---|
| 有效确认数（ground truth 成立） | 4（H1-H4：SQLi / XSSr / CMDi / LFI） | 4（H1-H4） | v2 ≥ 基线 | ✅ 持平 |
| 误报数（confirmed 但 ground truth 不成立） | **2**（H5 xoops、H6 phpLDAPadmin，来自 Scanner 告警） | **0**（H5/H6 killed） | v2 ≤ 基线 | ✅ 下降 |
| 重复调用率（归一化 method+URL+body） | 2/12 = **16.7%** | 1/11 = **9.1%** | v2 < 基线 | ✅ 下降 |

**三条验收全部达成**（task-breakdown T-050）。有效确认数持平符合预期：探测目录内的
4 个真实漏洞两版都能找到；差异集中在告警处置质量与冗余请求。

## 2. 关键过程差异（结构性，非操作者差异）

### 2.1 Scanner 告警处置（误报数 2 → 0）

同一份合成告警文件（nuclei-jsonl，3 条：1 真 2 假）注入两战役：

- **基线**：单 Agent 一体化，分诊 = 打开告警 URL 看返回 200 即采信，自我裁决
  confirmed（xoops / phpLDAPadmin 在靶场根本不存在）。v1 报告门禁只查证据角色
  齐全，无法拦截"证据齐全但结论错误"的自我确认。
- **v2**：`harvest` 强制 `requires_verification=true`、`confidence=0.5`（扫描器
  告警永不自动 confirmed）；Verifier 独立分诊抓特征（xoops / phpLDAPadmin 均
  0 次命中），refutation 证据驱动 killed 裁决；报告门禁额外校验 confirmed 的
  `verifier_run` 溯源。

### 2.2 重复调用（16.7% → 9.1%）

- 基线：登录页重复 GET（先无 cookie 探测再取 token）+ Scanner 分诊重开已测 URL
- v2：`pack/verify-pack` 最小上下文 + harvest 后告警 URL 不再盲目重放（先入账为
  待验证事实）；唯一重复是 Verifier 对 SQLi 的独立重放——这是设计内的独立复核，
  而非重复探索

### 2.3 v2 控制面全程实测通过

- `claim/lease`：R1(worker)、R2(verifier) 认领与完成事件回放正确
- 幂等 ingest：R1 同键重放返回 `duplicate`，账本逐字节不变（md5 一致）
- `state` 回放：Intent/Run 状态派生正确，findings = H1-H4
- `recall`：BM25+模糊+结构化+一跳图扩展可解释命中（失败路径 killed 并召）
- `render`：board.md / dashboard.html / attack-graph.{html,mmd} 离线四件套
- 报告门禁：三角色闭环 + 无未闭环 provisional + confirmed 必带 verifier_run → PASS

## 3. 边界与诚实披露

- 单操作者、单次运行，非盲测；命令由主 Agent 按各自 SKILL 纪律善意执行
- 基线的 2 个误报来自旧工作流**允许**的自我确认模式（协议第 2 节结构性差异），
  不代表旧版每次必然产生该误报
- 有效确认数未提升的原因：探测目录覆盖的真实漏洞基线已能全部确认；v2 的增益
  体现在质量（0 误报）与效率（重复率近半），符合"不虚标"
- 评测脚本 `append_v2.py` / `gate_check.py` 为评测专用（正式路径应走 CLI/ingest；
  v2 案件的 H/E/V 暂无 CLI 追加命令，见 §4）

## 4. 发现的改进项（转后续任务候选）

1. v2 案件缺少 H/E/V 追加 CLI（walking skeleton 走 v1 CLI 是因为该用例为纯
   v1 格式案件）；建议后续提供 `prism.py` 的记录追加命令或 ingest 支持裁决包
2. harvest 多条同资产告警合并为 1 条事实时，仅保留首条标题（W2/W3 标题只在
   digest 中）；建议合并时保留告警标题列表
3. 报告门禁的 v2 等价校验应下沉为 `prism.py` 正式命令（当前评测用脚本实现）

## 5. 结论

sapper-skill v2 控制面在真实靶场端到端可用：授权 Gate → Intent/claim → Worker
结果包 → 幂等 ingest → Verifier 独立复核 → 裁决 → 门禁 → 离线面板。对比基线，
误报数与重复调用率显著下降，有效确认数持平，**T-050 验收通过**。下一任务
T-051 多宿主验收。
