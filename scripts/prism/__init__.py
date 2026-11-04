"""prism v2 控制面（P1 骨架）。

模块：
- models：WorkerResult 协议模型与 schema 导出
- packets：Worker / Verifier 角色上下文包装配
- cli：Typer 命令面（schema / pack / verify-pack）

边界（升级方案 §4）：不实现模型 API、自主推理循环、子 Agent 进程管理、
目标 Shell/Exploit 执行、MCP Server、常驻服务。
"""
