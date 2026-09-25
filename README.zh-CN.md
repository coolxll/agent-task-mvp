# Agent Task MVP：使用说明

从 Mac 的网页选择一个 Git 工作目录和远端机器，在一个大文本框里描述需求。Manager 把当前已提交版本封装成任务包送往 Runner；远端 Codex 调查仓库、拆解步骤、实现、独立评审、运行测试并生成验收报告。结果以 Git bundle 回到 Mac。GitHub 项目在所有检查通过后可自动创建 PR；用户在网页验收通过后，Manager 合并 PR 并清理本次远端 worktree。

[实施计划与差距](docs/implementation-plan.zh-CN.md) · [逐项验收记录](docs/acceptance.zh-CN.md) · [本体 Agent 框架选择](docs/native-agent-framework.zh-CN.md) · [目标产品定义](docs/target-mvp.zh-CN.md)

## 快速体验

1. 确保本机 Manager、到 `corp172-dev` 的 SSH 转发和远端 Runner 在运行。打开中文版 <http://127.0.0.1:18765/zh>。
2. 在“任务”点击“选择文件夹…”，选一个 **已提交且干净的 Git 仓库**。系统读取路径、Git remote、当前提交与默认分支并创建或复用 Project。原有 Project 也可在下拉框选择。
3. 选择 `corp172-dev`，在“描述你想完成的需求”写下目标和限制，点击“创建并运行”。标题、验收条件、步骤和测试建议由 Agent 从需求中提取。
4. “执行流程”展示准备工作区、规划、实现各步骤、**Agent 代码评审**、测试和验收检查。若 Agent 缺少必要信息，Run 会停在“等待你补充信息”；打开该 Run，回答问题后会用保存的 Codex 会话继续同一阶段。也可取消。
5. “交付验收”是**用户对最终成果的决定**，不是 Agent 的代码评审。此页展示任务包、规划、代码评审、测试输出、验收证据、改动文件与 diff。满足检查条件时，Mac 已取回结果并显示 PR 链接或本地结果仓库路径。点击验收通过后，GitHub PR 会合并；选择“保留分支”的项目会在 Mac 上保留成果分支。拒绝则关闭已创建的 PR，并清理远端分支和 worktree。

仓库有未提交改动时，提交任务会报错并保留原工作树；先自行提交。每个任务固定到提交时的 HEAD，运行中本机继续改代码也不会改变远端任务输入。系统不会 checkout、stash、reset 或清理本机项目目录。

## 安装与连接

要求 Mac 有 Python 3、Git；远端有 Python 3、Git 和已登录的 `codex` CLI。两端用 `requirements.txt` 安装 Pydantic，用于校验 Agent 的计划、代码评审和验收输出。若要创建与合并 GitHub PR，Mac 还需要 GitHub CLI `gh` 登录并具有目标仓库的推送与合并权限。`corp172-dev` 不需要 GitHub 写权限。

第一次使用，在远端放置运行文件，并生成仅 Runner 使用的访问 token。已有 token 不要覆盖：

```sh
ssh corp172-dev 'mkdir -p /workspace/agent-task-mvp && chmod 700 /workspace/agent-task-mvp'
scp app.py agent_drivers.py control.py pipeline.py git_io.py ui.html ui.zh-CN.html ui.js corp172-dev:/workspace/agent-task-mvp/
scp requirements.txt corp172-dev:/workspace/agent-task-mvp/
ssh corp172-dev 'python3 -m venv /workspace/agent-task-mvp/.venv && /workspace/agent-task-mvp/.venv/bin/python -m pip install -r /workspace/agent-task-mvp/requirements.txt'
ssh corp172-dev 'python3 - <<'"'"'PY'"'"'
from pathlib import Path
import secrets
p = Path("/workspace/agent-task-mvp/token")
if not p.exists():
    p.write_text(secrets.token_urlsafe(32))
    p.chmod(0o600)
PY'
```

在远端运行：

```sh
/workspace/agent-task-mvp/.venv/bin/python /workspace/agent-task-mvp/app.py runner \
  --root /workspace/agent-task-mvp/data \
  --token-file /workspace/agent-task-mvp/token \
  --host 127.0.0.1 --port 8766 \
  --agent-access full
```

`corp172-dev` 的开发容器无法运行 Codex 默认的 `workspace-write` 沙箱；上述参数把 Runner 的 Agent 访问级别设为 Full access。当前 Codex 驱动会跳过工具权限确认，使工作流能无人值守地执行命令。它**不会替用户回答需求歧义**；Agent 可以明确提问并等待网页回答。Full access 作用于远端容器，Git worktree 只隔离代码目录，不提供操作系统权限边界。只在受信任的机器和项目中使用。Runner 绑定远端回环地址，只通过 SSH 端口转发连接。

在 Mac 的一个终端保持转发：

```sh
ssh -N -L 18766:127.0.0.1:8766 corp172-dev
```

另一个终端启动 Manager：

```sh
cd /Users/lynn/workspace/projects/agent-task-mvp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py manager --db manager.sqlite3 --host 127.0.0.1 --port 18765
```

在“配置”添加节点，名称 `corp172-dev`，地址 `http://127.0.0.1:18766`，token 从远端 `/workspace/agent-task-mvp/token` 读取。现有节点不必重复添加。Manager 默认仅监听本机回环地址；**不要直接暴露 Manager 端口到公网**，因为目录浏览与项目管理接口供本机用户使用。

## Project 与交付方式

选择本机目录会自动登记 Project。也可在“配置”手工创建：填写 Git URL，用 Runner 托管克隆；或填写远端已有 Git 仓库路径。Project、Node 和 Workspace 是长期配置；每次 Run 仍单独创建 worktree。

项目设置可以配置 Gate 命令（每行一条）、PR 目标分支及交付方式。留空 Gate 时 Planner 提出测试命令；配置了 Gate 时系统按项目 Gate 执行。命令由 Runner 在 worktree 中执行，应只配置可信项目。通过本机目录导入的 GitHub remote 会默认选择“创建 GitHub PR”；没有 GitHub remote 或手工创建的 Project 默认选择“取回 Mac 并保留分支”。可在“配置”修改。PR 的目标分支默认取 Git 的 `origin/HEAD`；识别不到时使用当前分支，提交前应检查项目设置。

远端只负责执行与产生结果。Manager 通过 Git bundle 导入 Mac 的 `manager.sqlite3.data/runs/<run-id>/result.git`；在 GitHub 方式下，用 Mac 的 Git/gh 推送任务分支并创建 PR，网页批准后以已审查的 commit SHA 合并。若 PR 分支被他人更新，审批会拒绝合并。GitHub 仓库保护规则仍会生效。失败的交付可在审核页重试。

## 数据与限制

- Manager 状态在 `manager.sqlite3`；任务包、输入和结果 bundle、Mac 上的结果仓库在 `manager.sqlite3.data/`。Runner 的 worktree、日志、计划和产出在 `--root` 目录。不要把这些运行数据提交到 Git。
- 每个任务目前选择一台启动机器，Planner 能生成最多 8 个依赖步骤，在该机器顺序执行。跨机器分配与代码交接还没有接入。
- 工作流依赖 `AgentProvider` / `AgentDriver` 接口，已实现多 Provider 统一适配：默认主力 Provider 为 `antigravity`（基于 Antigravity CLI/SDK，原生支持 `--json-schema` 结构化输出强约束、`--conversation` 原生断点续跑与规划/编辑模式隔离）；轻量兜底 Provider 为 `pi`（派 Agent，采用原生 JSONL RPC 协议 `pi --mode rpc` 双向通信，摆脱脆性的 CLI 命令行文本抓取，具备原生流式事件捕获、Session 原生持久化与 `--tools` 细粒度只读沙箱）；同时支持 `codex` 与 `claude` 驱动。Task 选择 Agent，Run 和任务包保存 `agent_kind`，Runner 按类型实例化驱动。Planner、实现、独立评审与验收各有 Agent 会话；同一阶段需要补充信息时，Runner 保存会话 ID、问题和阶段进度，回答后由驱动续跑，已完成阶段不会重跑。Agent 评审和验收会附证据，最终合并仍由用户在 Web 中决定。
- 规划、代码评审和验收的结构化输出由 Pydantic 模型生成 JSON Schema 并校验；步骤依赖无环、Gate 非空等业务规则仍由普通代码校验。本体 Planner 目前仍使用所选远端的 Codex，未来独立 Planner 的框架选择见[专项决策](docs/native-agent-framework.zh-CN.md)。
- PR 自动创建/合并只支持 `github.com` 仓库；其他 Git remote 可以把成果带回 Mac 并保留分支。真实 GitHub PR 需要一个有写权限的项目，当前试验使用本地 Git 仓库，因此验收记录明确区分本地集成验证与外部仓库实测。
- 本机仓库必须没有已跟踪或未跟踪的改动。Git bundle 输入上限 48 MiB。大型仓库可使用手工配置的远端已有目录；此时选择的是 Runner 上的代码，不会自动包含 Mac 的未提交内容。
- 等待用户输入时的状态和会话可持久保存；Runner Worker 在执行中异常退出后的自动侦测与恢复、自动修复循环、多 Manager、多节点步骤调度尚未实现。
