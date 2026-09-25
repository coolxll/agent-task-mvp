# 网页验收后合并到本机目录

## 使用方式

从网页导入一个干净的本机 Git 目录。新导入的 Project 默认使用“验收后合并到所选本机目录”；已有 Project 可在“配置”中切换到此方式。输入需求并选择 Node 后，远端在独立 worktree 完成任务，Manager 将结果 bundle 取回。用户在“交付验收”页查看 diff、Agent 评审与 Gate 后点击“验收通过并合并到本机”。此流程不需要 GitHub 或 `gh`。

Manager 只会将提交任务时选中的本机分支快进到**已审核的准确提交**。批准时重新检查分支、HEAD 和工作树；若用户切换分支、产生本地提交或留下未提交改动，合并失败并保留 Review 状态与结果仓库，用户可以自行处理后重试。合并成功后才通知 Runner 清理该 Run 的远端 worktree。原本的“保留分支”和 GitHub PR 方式仍可在项目设置中选择。

## 验收证据

- 隔离集成测试经 Manager API 提交任务、等待远端 Runner 完成、确认选中目录在网页批准前保持原提交、批准后 HEAD 等于已审核提交、文件内容更新且工作树干净；远端 worktree 清理，Run 交付状态为 `merged`。
- 另一隔离测试在 Review 时先向本机分支增加提交，验证网页批准被拒绝，本机 HEAD 保持新提交，Run 保持 `REVIEW`，随后可拒绝并清理远端 worktree。
- 真实远端验收：在 `/tmp/agent-task-local-merge-qa-20260925` 建立一次性 Git 仓库，Manager 使用 Pi 配置的 DeepSeek Flash 规划，`corp172-dev` 的 ACP Runner 实现修复、独立评审并运行 `python3 -m unittest -v`（退出码 0）。Run #13 到 `REVIEW` 后，Manager 收到的 diff 仅将 `calculator.py` 中的 `return a - b` 改为 `return a + b`；本机目录仍停在基准提交 `85ea8c1`。调用网页批准按钮所用的同一 `/api/runs/13/review` 接口后，Run 为 `SUCCEEDED`、交付为 `merged`，本机 HEAD 精确等于已审核提交 `729a752`，工作树干净且远端 worktree 已清理。
- 首次真实试跑 Run #12 在 Agent 评审运行 unittest 后，因测试仓库未忽略 `__pycache__` 而触发只读阶段文件指纹保护，明确失败并清理。给一次性仓库补充 `.gitignore` 后，Run #13 通过。该保护要求项目正确忽略测试生成文件。
- 本次真实任务的最终批准通过与网页按钮相同的 Manager API 完成；浏览器自动化入口不可用，未再次做按钮点击的视觉验收。没有对用户的实际项目目录执行合并。

## 运行环境

Mac Manager 和远端 Runner 都使用 `uv venv --python 3.12 .venv` 创建的项目虚拟环境，并从 `requirements.txt` 安装依赖。不要用系统 Python 直接启动 Manager。当前启动命令见[中文 README](../README.zh-CN.md)。
