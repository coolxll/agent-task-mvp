# ACP Runner 验收记录（2026-09-25）

## 实现边界

- `AcpDriver` 调用独立的 `acp_bridge.py`，后者使用官方 `agent-client-protocol==0.12.1` SDK 处理 JSON-RPC。Runner 通过 `ACP_AGENT_COMMAND` 配置实际 Agent；业务层只保存 `agent_kind=acp`。
- 已实现 `initialize`、`session/new`、`session/load`、`session/prompt`、事件日志、权限请求处理及进程组取消。Full access 时自动选择一次性允许选项；其他访问级别拒绝权限请求。ACP 的权限回调不构成 OS 沙箱。
- 表单/URL Elicitation 尚未接入 Web 等待与回答。当前仍沿用工作流已有的文本 `NEEDS_INPUT`，遇到 ACP Elicitation 请求会明确拒绝并记日志。不要把 `elicitation/complete` 当作用户回答。
- JSON 输出仅在 EOF 明确缺少闭合括号、补齐后能解析时修复；其余无效输出继续由 Pipeline 标记失败。

## 真实远端验证

测试机 `corp172-dev`，Python 3.12.3，`@agentclientprotocol/codex-acp@1.13.1`。使用独立测试 Runner 目录与临时 Mac Manager 数据库；输入是一个只有错误 `add(a,b)` 的本地 Git fixture。

| 场景 | 结果 |
| --- | --- |
| 握手、创建 Session、简单 Prompt | `PONG`，协议版本 1 |
| 编辑 `calc.py` | Agent 将 `a-b` 改成 `a+b`，执行结果为 5 |
| `session/load` | 用上一 Session ID 恢复并回答 `RELOADED` |
| 完整 Task | Planner、3 个实现步骤、Agent 代码评审、`python3 -m unittest discover -v` Gate、验收均完成；Run 进入 `REVIEW`，Mac Manager 取得结果 |
| Review 清理 | 对测试 Run 执行 Reject 后，Runner 返回 `REJECTED` 并清理本次 worktree |
| 失败路径 | 首轮验收 JSON 缺末尾 `}` 时 Run 为 `FAILED` 且保留明确错误；修复受限 EOF 恢复后重跑通过 |

本机 `.venv312/bin/python -m unittest discover -s tests -v`：19 项通过。测试未使用真实 GitHub 仓库，因此没有验证创建或合并 PR。测试任务最终选择 Reject，未替用户合并任何代码。

## 已知限制

`corp172-dev` 禁止非特权用户命名空间，Codex 默认 bubblewrap 沙箱无法启动；该测试 Runner 使用 Full access。worktree 隔离代码目录，不是进程安全边界。只读阶段仍依靠 worktree 指纹检查发现改动；若需要强只读，应另加 OS 权限隔离。当前事件进入 Runner 日志，Manager 仍按原有轮询取得日志；SSE 和 UI 事件时间线属于后续 PR。
