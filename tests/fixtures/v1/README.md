# v1 冻结 Fixture（T-010 冻结，禁止改写）

## 用途

- 作为 **v1 账本行为的黄金样本**，供 `tests/test_fixture_v1.py` 守卫
- 作为 **v1→v2 迁移（T-030）的输入**：schema v2 迁移脚本必须能完整转换本 fixture 且不丢语义

## 内容清单

`case/ledger.jsonl`（20 条记录）覆盖全部记录类型与裁决状态：

| 假设 | 状态 | 覆盖点 |
|---|---|---|
| H1 | confirmed | 三角色证据闭环（E1 观察 / E2 复现 / E3 影响） |
| H2 | killed | refutation 角色 + refutes 效果反证（E4） |
| H3 | provisional | 开放状态：仅观察+复现，缺影响 → **报告门禁应拒绝** |
| H4 | deferred | 暂缓：证据保留、裁决延后 |
| H5 | active | 无裁决假设（E8 仅观察） |
| H6 | inconclusive | 无定论裁决 |

`case/artifacts/`（6 个文件）：全部使用保留地址（192.0.2.0/24、example.com），无真实目标数据。

`case/evidence-validation.md`：由 `render` 生成的派生报告（含黑板快照），随 fixture 一并冻结作为 golden 输出。

## 再生方式（时间戳已用 `--at` 固定，输出确定）

```bash
# 在项目根目录、激活 .venv 后执行；逐条命令见 git 历史
# tests/fixtures/v1/case 由 scripts/case_ledger.py 生成
python -X utf8 scripts/case_ledger.py verify tests/fixtures/v1/case
```

冻结规则：**任何对 ledger.jsonl 的手工编辑都违规**；需要变更时新增 fixture 版本目录（如 `fixtures/v2/`），不修改本目录。
