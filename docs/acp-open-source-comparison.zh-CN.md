# ACP 开源实现对照（2026-09-25）

## 对照对象

- [ACP 官方 Python SDK](https://github.com/agentclientprotocol/python-sdk/tree/9d07d7871ef4b220b8507e15fc4b1560f0950a64/examples)：我们已使用其 `connect_to_agent`；示例展示权限回调、`session/cancel`、文件/终端能力和 Elicitation。
- [acpx](https://github.com/openclaw/acpx/tree/689b1f6a8acb2cdefb588f0fcf7cd2b6ef20d317)：成熟的命令行/嵌入式 ACP Host，重点参考[权限策略](https://github.com/openclaw/acpx/blob/689b1f6a8acb2cdefb588f0fcf7cd2b6ef20d317/docs/permissions.md)、[会话控制](https://github.com/openclaw/acpx/blob/689b1f6a8acb2cdefb588f0fcf7cd2b6ef20d317/docs/session-control.md)与[进程生命周期](https://github.com/openclaw/acpx/blob/689b1f6a8acb2cdefb588f0fcf7cd2b6ef20d317/docs/runtime-process-lifecycle.md)。
- [acp-ui](https://github.com/formulahendry/acp-ui/tree/cd9c3cb464a4b321bff652101953a64c07473e31)：桌面/Web Client，重点参考[权限请求队列与传输关闭处理](https://github.com/formulahendry/acp-ui/blob/cd9c3cb464a4b321bff652101953a64c07473e31/src/lib/acp-bridge.ts)和[权限选择 UI](https://github.com/formulahendry/acp-ui/blob/cd9c3cb464a4b321bff652101953a64c07473e31/src/components/PermissionDialog.vue)。
- [ACP v1 Elicitation 规范](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v1/elicitation.mdx)：区分表单和 URL 模式；只有 Client 明确声明的模式才能由 Agent 请求。

## 与当前实现的差异

| 主题 | 当前平台 | 借鉴点 |
| --- | --- | --- |
| 协议实现 | `acp_bridge.py` 已使用官方 Python SDK 完成握手、新建/加载会话、Prompt 和事件接收 | 继续使用 SDK，不自行实现 JSON-RPC 或传输层 |
| 权限 | Full access 自动选 `allow_once`，若没有则回退到 `allow_always`；其他级别直接取消 | `acpx` 把权限模式、单项策略、无法交互时的失败行为分开。我们应避免静默选择持久授权，并把待决请求绑定到当前 Run/Turn |
| 人工输入 | 文本 `NEEDS_INPUT` 可续跑；ACP Elicitation 目前明确拒绝 | 按规范先实现表单请求的持久化、网页展示、回答/拒绝/取消；URL 模式单独处理，不把 `elicitation/complete` 当回答 |
| 会话 | 每个 Pipeline 阶段启动新的桥接和 Agent 子进程；只在阶段暂停后用 `session/load` | `acpx` 有会话所有者、串行 Turn、状态和合作式 `session/cancel`。我们需要 Run/Stage/Turn 归属和重启后的状态核对，避免用 PID 或 Session ID 单独判断存活 |
| 取消 | Runner 发送进程组 SIGTERM | 先尝试 ACP `session/cancel`，限时等待；不响应再终止进程组。记录最终 stop reason |
| 事件 | 工具标题/状态写入日志，再经 Manager 轮询和网页 SSE 展示；其余消息多为文本 | 保留 ACP 原始事件类型和关联 ID，用稳定事件序号关联工具调用、更新、权限请求和最终结果 |
| Client 能力 | 当前 `ClientCapabilities()` 不声明文件/终端能力 | 保持这个边界；只有确实需要 Host 执行文件或命令时，才实现路径校验和生命周期检查后声明能力。声明能力不等于 OS 沙箱 |
| 测试 | 已在 `corp172-dev` 用 `codex-acp` 跑通一次真实 Task；单元测试主要覆盖参数交接和 JSON 收尾 | 借鉴 `acpx` 的模拟 Agent/一致性用例，覆盖权限、取消、断连、会话加载、迟到回答和多事件顺序 |

## 建议落地顺序

1. **先修权限语义**：Full access 只自动选一次性允许；若 Agent 仅提供持久允许，应显式失败或进入 Human Needed。把权限决定与 Run、Stage、Turn 和请求 ID 绑定，Turn 结束后拒绝迟到回答。
2. **补协议级取消和可观测性**：为在途 Prompt 保存 Session ID 与状态；取消时先发送 `session/cancel`，超时再终止进程。事件存储保留工具调用 ID 与类型。使用模拟 Agent 覆盖竞争条件。
3. **实现 ACP 表单 Elicitation**：在 Manager 持久化请求并通过现有 SSE 呈现，网页提交结构化回答后再回复同一条 ACP 请求。URL 模式及认证流程在有实际需求时单独实现。
4. **再评估是否复用 `acpx` 运行时**：它是 TypeScript/Node 组件，而 Runner 当前是 Python。先用同一个一次性仓库做 `acpx` 小规模验收，比较授权、取消、事件、Session 恢复与进程清理；只有确实减少维护成本时再替换 Python 桥接。当前无须同时维护两个 ACP Host。

本对照是源码和文档检查，不代表上述新能力已经实现或经过远端验收。现有真实验收见 [ACP Runner 验收](acp-acceptance.zh-CN.md)。
