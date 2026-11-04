# ADR-0013 实时面板服务与双语界面重设计

- 状态：已接受（2026-11-04）
- 关联：ADR-0011（离线渲染）、ADR-0012（命名）

## 背景

用户提出三项 P4 增量需求：① 产物是否实时更新？要求提供可随时启停的实时
可视化与全局状态页；② dashboard/attack-graph 视觉简陋，需按设计规范重做
（浅色主题）；③ 界面文案中文化/双语。

原设计（ADR-0011）是**离线快照**：`render` 一次性生成，状态变化后需重跑，
不伪称实时推送。这不满足"随时掌握整体进展"的需求。

## 决策

### 1. 实时能力：`prism.py serve`（新增 `scripts/prism/live.py`）

- 本地 HTTP 服务（默认 127.0.0.1:8765）：静态托管 `dashboard/` 产物 +
  `/api/state`、`/api/version`、`/api/live` 三个端点
- 监听线程轮询 `ledger.jsonl` 指纹（mtime/size → sha256），变化即自动
  `render_all`；前端轮询 version 指纹，变化时平滑 `location.reload()`
- **启停**：交互式启动时询问"是否开启实时可视化？"（`--live/--no-live`
  跳过询问；非交互默认开启）；运行中随时 POST `/api/live` 暂停/恢复，
  dashboard 页内也有切换按钮；Ctrl-C 退出
- **离线退化**：同一份产物在 file:// 打开时自动停止轮询、显示"离线快照"，
  保持 ADR-0011 的单文件离线语义；不产生控制台噪音
- 硬约束不变：JSONL 只读；文件服务限制在 dashboard 目录内（防路径逃逸）；
  默认仅绑定 127.0.0.1

### 2. 视觉重设计：工业实用（Industrial / utilitarian）· 浅色

- 方向锁定：仪表盘密度、等宽数字（tabular-nums）、发丝边框、状态色体系
- 主色暖纸白 `#f2f0ea` / 表面 `#fbfaf7` / 墨色 `#211e19`；单一强调色
  信号橙红 `#c2451e` 只给 finding 与关键动作；蓝φ图网格底纹 + 四角标尺
  框头部为记忆点
- 字体本地栈（离线硬约束禁用 webfont）：Bahnschrift（DIN 系展示/数字）+
  Microsoft YaHei UI（正文）+ Cascadia Mono/Consolas（ID）
- 入场序列错峰 80ms、悬停反馈、`prefers-reduced-motion` 全量降级、
  `:focus-visible` 可见焦点圈、状态覆盖（空态折叠 + 空态提示）

### 3. 双语界面

- HTML 端：`data-zh` / `data-en` 属性字典切换，默认中文，页内 EN/中 按钮
- board.md / attack-graph.mmd：节标题与标签中英并列（如
  `## Findings（已确认发现）`、`资产 asset: <target>`）；状态标签中文优先
  （已确认/已证伪/执行中…），英文原词保留供机读兼容

## 影响

- `render.py`：模板与图标签重写；`board/mmd` 仍确定性（同 --now 逐字节一致）
- 新增 `live.py` + CLI `serve` 命令；`test_live.py` 11 项锁定
- T-050 评测面板已用新版重渲染；其余命令面行为不变
