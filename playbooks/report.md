# Report — 报告门禁与输出

> REPORT 阶段先过机器门禁，再写人类报告；门禁失败必须回到执行阶段补证据。

## 门禁（必须全部通过）

```bash
python -X utf8 scripts/prism.py verify <case>   # 必须输出 REPORT gate: PASS
```

1. **完整性**：v2 账本回放合法、无重复 ID、引用完整、哈希全部匹配。
2. **报告门禁**：全部 confirmed 三角色（observation / reproduction / impact）闭环且带 `verifier_run` 溯源；无未闭环 provisional。
3. v1 账本不能直接过门禁：先 `prism.py migrate <v1_case> --out <v2_case>` 再续跑。

## 披露要求

- **Confirmed**：逐条列出 claim / 范围 / 证据链（observation → reproduction → impact）/ 裁决理由。
- **Killed**：列出反证与证伪条件（证伪同样有价值）。
- **Inconclusive / Deferred**：明确披露原因与建议后续动作，不得静默丢弃。
- **Cleanup**：Worker Result 中登记的清理项逐条核对处置状态；未处理项必须显式列出。
- **限制**：无法机器验证的内容（如"完全独立的验证"）如实写限制，不虚标。

## 输出

- 人类报告：`case/dashboard/`（`prism.py render` 生成，禁止手工维护；删除后重建）。
- 引用证据时给 artifact 路径与 SHA-256，不复制敏感原文；秘密不出现在摘要。
- Focused 模式小闭环可直接在回复中输出以上结构，同样满足披露要求。
