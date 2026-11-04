# ADR-0011: 离线面板与攻击图渲染

- **状态**：Accepted
- **日期**：2026-11-04
- **关联任务**：T-041（P3 可视化）
- **关联决策**：ADR-0007（v2 状态模型，回放即投影）

## 背景

升级方案 §9 要求"用户随时能看懂当前执行状态和攻击链"，但通用 Skill
不应承诺跨宿主一致的实时 Web 服务。采用三层可见性中的第 3 层：
离线自动重建面板。

## 决策

### 1. 四个产物，单文件离线打开

`prism.py render <case>` 生成到 `<case>/dashboard/`（可 `--out-dir`）：

- `board.md`：NOW、Active Runs、Ready/Blocked Intents、Findings、
  Cleanup——宿主直接可读的紧凑文本视图；
- `dashboard.html`：Jinja2 生成，内联 CSS 与原生 JS 过滤（输入关键词
  按目标/状态/ID 过滤表格行），Findings / Hypotheses / Intents / Runs /
  Approvals 分表；页面明示"离线快照，重新 render 刷新"，不伪称实时推送；
- `attack-graph.html`：PyVis 交互图（缩放/拖拽/着色/节点详情）；
- `attack-graph.mmd`：Mermaid 文本（攻击链 + Fact→Intent→Run 诊断两个
  subgraph），宿主可直接渲染。

### 2. 离线是硬要求

PyVis `cdn_resources="in_line"` 把 vis-network 全量内联；pyvis 0.3.2
模板仍会注入未使用的 bootstrap CDN 外链（纯装饰），渲染后统一剥离
（`_strip_external_refs`）。测试机读校验：两个 HTML 中不存在任何
`src/href="http(s)://`。

### 3. 图与账本一致：回放即投影

全部节点/边从账本回放派生，不引入第二数据源：

- fact(asset) → 资产节点；fact(service/application) → 服务节点并连到
  所属资产（host:port 解出 host）；
- 假设按资产族口径（与 recall 的主机抽取规则一致，复用
  `recall._HOST_RE`，保证"图"与"召回"对同一账本得出同一拓扑）连到
  其 claim/scope 引用的资产与服务；latest verdict = confirmed 的假设
  投影为 finding（高亮）；
- intent→run 诊断链、linked_facts→intent 边如实呈现。

### 4. 派生物可删除重建，JSONL 只读

render 只读账本；board.md / attack-graph.mmd 确定性输出（同 `--now`
逐字节一致，节点/边/行全部排序）；HTML 中 PyVis 的随机布局在 JS 端
执行，文件级重建不保证逐字节，但节点/边数据一致由测试锁定。
`--now` 同时用于 board/dashboard 的时间戳确定性。

### 5. 大图降噪阈值

节点超过 500 时过滤非 finding 假设节点（当前案件规模全量渲染）；
聚焦一跳的按需子图属宿主 adapter 可选增强，不在 Core 承诺内。

## 影响

- 满足 P3 出口"用户随时能看懂当前执行状态和攻击链"
- SQLite 物化缓存继续延迟：渲染直接消费回放产物，接口不变
- Cleanup 机器状态显示占位说明（该记录类型随 P4 报告门禁落地）
