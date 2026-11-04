# 编码与提交规范

## 1. 语言与运行时

- Python 3.10+
- TypeScript 仅作为历史参考，不进入本项目实现
- Shell 脚本不作为主要实现语言

## 2. 代码风格

- Python：PEP 8，类型注解必填
- 格式化：`ruff format`
- 静态检查：`ruff check` + `mypy`
- 命名：
  - 模块：`snake_case`
  - 类：`PascalCase`
  - 常量：`UPPER_SNAKE_CASE`
  - CLI 命令：小写中划线或单词

## 3. 目录纪律

- 业务代码只放 `scripts/prism/`
- 测试只放 `tests/`
- 文档只放 `docs/`
- 参考快照只放 `reference/projects/`
- 临时输出只放 `workspace/` 或 `case/`
- 禁止在根目录散落临时文件

## 4. 提交规范

### Commit Message

```text
<type>(<scope>): <subject>

<body>

<footer>
```

类型：

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `docs` | 文档变更 |
| `refactor` | 重构 |
| `test` | 测试 |
| `chore` | 构建/依赖/工具 |
| `spec` | 需求或设计变更 |
| `state` | 任务/进度状态更新 |

示例：

```text
spec(auth): define approval key semantics

- Add action class + target scope + effect grouping
- Record approval in Run
- Update open questions with pending host list
```

### 分支策略

- `main`：始终可运行的稳定状态
- `feat/<task-id>-<short-desc>`：功能开发
- `docs/<topic>`：文档更新
- `fix/<bug-id>`：缺陷修复

### 提交纪律

1. 每个提交只做一件事
2. 提交前必须通过：
   - `ruff check`
   - `ruff format --check`
   - `mypy`
   - `pytest`
3. 文档与代码同属一个逻辑变更时，应在同一提交或紧邻提交中完成
4. 禁止提交本地临时文件、缓存、生成的 `case/` 数据

## 5. 文档同步规则

- 修改需求 → 必须同步评估 `design`、`plans`、`state/TASKS.md`
- 修改设计 → 必须先写 ADR
- 修改任务状态 → 必须追加 `state/PROGRESS.md`
- 修改对外行为 → 必须更新 `state/CHANGELOG.md`

## 6. 安全编码底线

- 不在代码或文档中硬编码真实凭据、目标 IP 或客户数据
- 示例一律使用保留地址或占位符
- 任何涉及目标执行的代码都必须经过 scope-check
- 不引入未审计的第三方依赖
- 依赖变更必须通过 ADR 记录理由
