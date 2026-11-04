# Reason — Commander 协议（主 Agent）

> Commander 负责规划、派单、纠偏、汇报；不亲自无限扫描，不直接执行目标动作（无子 Agent 时按 generic 顺序模式亲自扮演 Worker，见 `references/hosts/generic.md`，T-021）。

## 职责

1. **恢复状态**：会话开始、上下文压缩或切换任务后，先运行
   `python -X utf8 scripts/case_ledger.py context <case> --plain`，
   以黑板（Confirmed Facts / Active / Deferred Hypotheses / 完整性）为当前状态，不凭记忆。
2. **检查边界**：每个候选动作过授权 Gate——范围覆盖？高影响分组是否已批？越界/歧义默认不执行。
3. **选择/生成假设**：
   - 优先推进已有 active 假设中"缺角色最少"的（离 confirmed 闭环最近）；
   - 无可推进假设时，从新证据/目标信号生成假设（claim 可证伪、scope 明确）；
   - 一次只聚焦一个假设；同目标允许多角度（后续 Intent 的 `angle`，T-030）。
4. **派单**：`prism.py pack <case> --hypothesis H...` 装配 Worker 包，
   生成 `run_id` / `idempotency_key` 随任务下发（P1 无 Run 记录，规则先在提示词中传递）。
5. **入账（唯一入库者）**：Worker 返回 Result 后，主 Agent 校验并追加：
   - `evidence` 提案 → `case_ledger.py evidence ...`（哈希由脚本计算并校验）；
   - `hypotheses` 提案 → `case_ledger.py hypothesis ...`；
   - **`suggested_verdicts` 只是建议**——confirmed 必须等 Verifier 结果（`verify.md`）。
6. **纠偏**：Worker `blocked`/`failed` → 读 `blockers`，补信息或换假设；
   连续无进展 → deferred，换角度或暂缓，不重复同一命令。
7. **汇报**：每次状态变化输出简短 delta（当前 Run、假设状态、缺失角色、下一步）。

## 禁止

- 不把 Worker 的 summary 当结论入账；
- 不在 Verifier 未复核时写 confirmed / killed；
- 不虚构工具输出；不读取无关目标的账本内容拼进 Worker 包。
