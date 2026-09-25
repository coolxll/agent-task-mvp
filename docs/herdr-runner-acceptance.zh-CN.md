# Runner 与 Herdr / Paseo 运行架构打通

## 概述与设计

本项改动为 Runner 引入了 **`HerdrDriver`（终端多路复用驱动）** 与 **`PaseoDriver`（守护进程驱动）**，彻底解决了远程长任务容易受 SSH 断连影响、进程无法挂后台保活、以及人类无法随时 Attach 接管的问题。

### 1. Herdr 多路复用驱动 (`herdr`)

通过 `herdr_bridge.py` 桥接层与本机的 Herdr 守护进程进行通信：
1. **持久化窗格分配 (Pane Split)**：在目标 worktree 工作目录中，通过 `herdr pane split --cwd <workspace> --direction right --no-focus` 分裂独立后台窗格，返回稳定 `pane_id`（如 `wJ:p2`），即使网络断开，该终端会话依然由 Herdr Server 守护保活。
2. **生命周期纳管 (Agent Start)**：通过 `herdr agent start <name> --kind <claude|codex|agy> --pane <pane_id>` 启动目标 Agent，Herdr 自动跟踪其 `idle`、`working`、`blocked`、`done` 状态。当使用 Full access 时，自动追加原生 bypass 标志（如 Claude 的 `--permission-mode bypassPermissions` 或 Codex 的 `--dangerously-bypass-approvals-and-sandbox`）。
3. **任务交互与产出回收 (Prompt & Read)**：通过 `herdr agent prompt <name> "<prompt>" --wait` 下发需求，等待 Agent 状态回归，通过 `herdr agent read` 完整抓取终端输出并持久化至 `result_path`。
4. **人类随时接管与审计**：在终端运行 `herdr attach <target>` 或 `herdr pane read`，人类开发者可以像操作 tmux 一样无缝接入远端现场。

### 2. Paseo 守护驱动 (`paseo`)

对于部署了 `@getpaseo/server` 的环境，支持通过 `paseo run --cwd <workspace> <prompt>` 直接将任务派发至 Paseo 后台守护集群，支持结构化 JSON Schema 约束与会话生命周期管理。

### 3. 验收验证

- `tests/test_herdr_driver.py` 验证：
  - `herdr` 与 `paseo` 成功注册至系统的 `available_kinds()` 中；
  - `HerdrDriver.session_id` 能够从日志流中精确解析 `[herdr.session] <pane_id>`；
  - `HerdrDriver.start` 正确构建桥接参数，包括工作区、提示词文件、权限级别与只读/结构化标志；
  - `PaseoDriver.start` 正确构建 CLI 调用。
- 完整 33 项回归测试全部通过。
