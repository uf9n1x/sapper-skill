# ADR-0005：全量主依赖一次锁定

- **状态**：已接受
- **日期**：2026-11-03

## 背景

T-011（P0 依赖与骨架冻结）要求生成 `requirements.lock`。设计文档（升级方案 §4）已规划 12 个主依赖：pydantic、typer、rich、PyYAML、filelock、rank-bm25、jieba、rapidfuzz、networkx、jinja2、pyvis、python-frontmatter。open-questions Q2 状态为"方向已确认，具体版本未锁定"。

两个候选策略：

1. 全量一次锁定并安装验证
2. 只锁 P1 必需（pydantic/typer/rich/PyYAML），其余随 P2/P3 递增锁定

## 决策

- 采用方案 1（用户已确认，2026-11-03 会话）
- 依赖声明放 `scripts/pyproject.toml`（与未来 prism 包实现同域），版本约束为固定兼容范围
- `scripts/requirements.lock` 与 `scripts/requirements-dev.txt` 由 `uv pip compile` 生成（主依赖 / dev extra），**禁止手工编辑**
- 锁定后全部装入 `.venv` 验证：`tests/test_dependency_lock.py` 逐项校验"可导入 + 安装版本与 lock 一致"

## 锁定结果（2026-11-03，Python 3.13.13）

pydantic 2.14.2 / typer 0.27.3 / rich 14.3.4 / PyYAML 6.0.3 / filelock 3.32.7 /
rank-bm25 0.2.2 / jieba 0.42.1 / rapidfuzz 3.14.6 / networkx 3.7 /
jinja2 3.1.6 / pyvis 0.3.2 / python-frontmatter 1.3.0；dev：pytest 9.2.0 等（见 requirements-dev.txt）

## 后果

- 优点：P1/P2/P3 各阶段直接使用，lock 不再频繁变更；新环境一条命令可复现
- 代价：提前安装 P3 检索/可视化依赖（约几十 MB）；jieba 在 Python 3.13 有第三方 SyntaxWarning（无害，已在 pytest.ini 过滤）
- 升级依赖必须重走本流程：先 ADR 记录理由 → 调整 pyproject 版本范围 → 重新 compile → 全量测试回归
- 锁文件不含哈希校验（离线分发方案在 P4 私有打包时再定，见 open-questions Q7/Q8 相关项）
