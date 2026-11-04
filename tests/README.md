# tests

> 测试策略见 `../docs/engineering/testing.md`；运行前提：`.venv` 已按 `scripts/requirements.lock` + `scripts/requirements-dev.txt` 安装。

## 运行

```bash
. .venv/Scripts/activate
python -m pytest tests/ -q
```

## 当前结构（P0 基线）

```text
tests/
  conftest.py                   # 共享夹具：ledger 模块加载、run_cli（-X utf8）、案件目录
  test_ledger_unit.py           # v1 账本单元回归：校验、门禁、语义、黑板、append 持久化
  test_ledger_cli.py            # v1 账本 CLI 端到端：生命周期、拒绝、尾行修复、原子报告
  test_skill_authorization.py   # 授权纪律机读门禁：反向规则回归即失败
  test_fixture_v1.py            # 冻结 fixture 守卫（也是 T-030 迁移输入的契约）
  test_dependency_lock.py       # 锁定依赖冒烟：可导入、版本与 lock 一致
  fixtures/
    v1/                         # 冻结 v1 黄金样本（禁止改写，见 fixtures/v1/README.md）
```

## 纪律

- v1 行为测试是**回归锁**：失败意味着既有正确行为被破坏，不是"测试需要更新"
- `scripts/case_ledger.py` 为冻结基线（与 reference 快照逐字节一致），lint 豁免至 T-030 迁移
- 新增依赖必须先走 ADR 并重新 `uv pip compile`，禁止手改 `requirements.lock`

## 后续计划（随 P1/P2 落地）

- `test_result_schema.py`：Worker Result Pydantic 契约（T-020）
- `test_ingest.py` / `test_recovery.py`：幂等入库与崩溃恢复（T-031）
- `test_render.py`：面板与报告投影（T-041）
- 属性测试（hypothesis）与多进程并发测试（T-031）
