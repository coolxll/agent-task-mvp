# 平台与 Agent 交互协议演进：走向 Agent Client Protocol (ACP)

本文档系统性论述 `agent-task-mvp` 平台与 Coding Agent 交互协议的演进方向，重点分析由 Zed、JetBrains 等发起的 **Agent Client Protocol (ACP)** 标准，并结合本地已下载的 Pi Agent 源码与官方 ACP Python SDK，给出平台的落地架构方案。

---

## 一、为什么与 Agent 的交互必须走向协议化？

在早期的原型与 MVP 实现中，调度系统往往采用粗暴的“命令行执行”模式：

```
Runner  ──(启动子进程)──>  codex / claude / agy -p "需求说明"  ──(管道重定向)──>  stdout/stderr
```

这种模式在面对生产级多阶段编排、长上下文治理与人机交互时暴露出致命缺陷：

| 痛点维度 | 命令行模式 (CLI `-p` + stdout 抓取) | 原生协议模式 (ACP / RPC) |
| :--- | :--- | :--- |
| **可观测性** | 依靠解析终端 ANSI 文本输出，容易被进度条、格式化混淆 | 结构化事件流（`tool_call`, `message_update`, `thought_chunk`）实时推送 |
| **状态与续跑** | 人机交互时盲猜会话 ID，甚至需要文本正则匹配问题 | 协议级 Session ID 与明确的提问（Elicitation）状态机响应 |
| **执行安全性** | 信任 Agent 自身是否遵守规则（如只读阶段全靠 Prompt 祈祷） | **反向控制**：由 Runner 托管文件系统与终端执行，对越权操作物理拒绝 |
| **生命周期控制** | 依赖 SIGTERM/SIGKILL 强制杀进程，可能造成文件半写或孤儿进程 | 标准化 `abort` / `cancel` 请求，支持 Agent 优雅析构与清理资源 |
| **厂商与多模型解耦** | 每接入一家 Agent 就需要写一整套特定的命令行拼装逻辑 | 类似 LSP（语言服务器协议），实现“一次接入，支持所有 ACP 兼容 Agent” |

---

## 二、参考源码库深度调研（已下载至 `reference/`）

在项目 `reference/` 目录下，我们分别引入了三份核心参考实现：

### 1. `reference/pi` (@earendil-works/pi-coding-agent)
Pi 是一个轻量级、开源且支持多模型的自包含 Coding Agent，其设计具备清晰的微内核结构：
- **`packages/protocol`**：定义了完整的 JSONL RPC 协议，包含会话生命周期、命令（`prompt`, `get_state`, `get_last_assistant_text`, `abort`）与事件（`tool_call`, `agent_settled`）。
- **`packages/coding-agent`**：核心 Agent 循环，负责工具调度（read, write, edit, bash）、模式管理与上下文压缩。
- **`packages/client`**：官方提供的 RPC Client 实现，通过 stdin/stdout 流与后台 Agent 建立长效交互。

### 2. `reference/agent-client-protocol` (Zed / JetBrains 官方 ACP 规范)
ACP 是当前 AI 开发者工具领域最主流的开放标准，致力于成为 **“Coding Agent 领域的 LSP”**：
- **JSON-RPC 2.0 基础**：协议规范基于双向 JSON-RPC 2.0，可在 `stdio`、SSE 或 WebSocket 上传输。
- **能力握手 (Handshake)**：双方通过 `initialize` 交换能力集（`ClientCapabilities` / `AgentCapabilities`），实现向后兼容。

### 3. `reference/acp-python-sdk` (官方 ACP Python SDK)
官方基于 Python `asyncio` 与 Pydantic 提供的完整 SDK：
- **客户端抽象 (`acp.Client`)**：
  - `fs/read_text_file` & `fs/write_text_file`：Agent 发起读写请求，由 Client (Runner) 实际执行。
  - `terminal/create`, `terminal/output`, `terminal/kill`：终端命令统一在 Client 监管下执行。
  - `create_elicitation`：Agent 请求用户补充信息。
  - `session_update`：流式接收消息分片、计划树变动与思考过程。
- **长连接管理 (`ClientSideConnection`)**：管理会话创建（`new_session`）、提示词下发（`prompt`）与异常通知。

---

## 三、ACP 在 `agent-task-mvp` 中的落地架构设计

在 ACP 体系下，平台角色发生根本性转变：**Runner 成为 ACP Client (Host)，Agent 成为 ACP Server (Guest)**。

```mermaid
sequenceDiagram
    autonumber
    participant Pipeline as Runner Pipeline
    participant Host as Runner ACP Host (Client)
    participant Agent as ACP Coding Agent (Guest)
    participant User as Web UI / Manager

    Note over Pipeline,Agent: 阶段 1: 初始化与沙箱准备
    Pipeline->>Host: 启动阶段 (如 PLANNING, readonly=True)
    Host->>Agent: initialize (capabilities: read-only fs, no terminal)
    Agent-->>Host: initialize response (capabilities)
    Host->>Agent: session/new (cwd=workspace)

    Note over Pipeline,Agent: 阶段 2: 任务下发与流式交互
    Host->>Agent: session/prompt (需求说明 + Output Schema)
    loop 事件驱动与工具反向调用
        Agent-->>Host: session_update (thought / plan / message)
        Host-->>Pipeline: 实时流式记录日志与阶段状态
        Agent->>Host: fs/read_text_file (path="calculator.py")
        Host-->>Agent: 文件内容
        alt Agent 尝试在只读阶段写文件
            Agent->>Host: fs/write_text_file (path="calculator.py")
            Host-->>Agent: Error (Permission Denied: read-only stage)
        end
    end

    Note over Pipeline,User: 阶段 3: 遇到歧义，原生挂起
    opt Agent 缺少必要信息
        Agent->>Host: create_elicitation (question="请问目标 Python 版本是？")
        Host->>Pipeline: 抛出 NeedsInput(question)
        Pipeline->>User: 状态置为 NEEDS_INPUT
        User->>Pipeline: 提交回答 "Python 3.11+"
        Pipeline->>Host: 恢复运行
        Host->>Agent: complete_elicitation (answer="Python 3.11+")
    end

    Note over Pipeline,Agent: 阶段 4: 运行完结与交付
    Agent-->>Host: session_update (AgentMessageChunk: 结构化 JSON 成果)
    Host->>Pipeline: 提取结构化验证结果并入库
```

### 核心收益

1. **绝对物理沙箱（Absolute Host-enforced Sandbox）**：
   在现有的实现中，只读阶段需要依赖 Agent 自己不写文件，并在事后对比 Git `write-tree` 指纹；在 ACP 模式下，Agent **必须通过 Client 提供的 `fs/write_text_file` 写文件**，Runner 在只读阶段直接拒绝对接，模型从物理上不可能污染工作区。
2. **完美对齐 `NEEDS_INPUT` 交互协议**：
   ACP 的 `create_elicitation` / `complete_elicitation` 与平台现有的人机提问/解答恢复机制天然契合，使交互逻辑从“文本协议（`NEEDS_INPUT: xxx`）”升级为“类型安全协议”。
3. **插件式 Agent 生态**：
   Runner 不需要感知当前跑的是 Pi、Claude Code、Codex 还是 Antigravity。只要它们符合 ACP 规范，即可通过同一个 `AcpDriver` 无缝调度。

---

## 四、演进路线规划

- [x] **第一阶段（已完成）**：Multi-provider 架构解耦，实现基于双向 JSONL RPC 的 `PiDriver` (`pi --mode rpc`)，摆脱 CLI `-p` 单次调用的粗糙模式。
- [ ] **第二阶段（ACP Driver 引入）**：
  - 基于 `reference/acp-python-sdk` 封装通用的 `AcpDriver`。
  - 在 Runner 内部实现标准 `Client` 接口，托管 worktree 文件读写与命令执行。
- [ ] **第三阶段（Agent 生态标准化）**：
  - 为不支持原生 ACP 的 CLI（如早期 Codex）配置轻量级 ACP Adapter 包装器。
  - 将 Pi Agent 官方或社区的 ACP 模式接入为平台的开箱即用引擎。
