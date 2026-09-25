# Herdr Runner 真实闭环验收（2026-09-25）

## 范围

本次在 Mac Manager（`127.0.0.1:18765`）和 `corp172-dev` Runner（远端 `127.0.0.1:8766`）之间，使用 `herdr` Agent Driver、Codex、系统管理的 Git 克隆及 worktree，验证任务执行到本机审核合并。测试项目是一次性仓库 `/tmp/agent-task-herdr-e2e-20260925`，不是产品仓库。

## 操作和结果

1. Manager 中已有 Project #7、Node `corp172-dev`。提交需求“修复 calculator.add 的错误，让现有 unittest 通过”，选择 Manager Planner、Herdr Driver、Full access；Project Gate 为 `python3 -m unittest -v`，交付方式为本机合并。
2. Run #16 在远端创建独立 worktree，按 Planner 的两个步骤分别启动 Codex，随后执行 Code Review 和 Acceptance。每个阶段使用独立的 Herdr workspace；完成后关闭该 workspace。
3. Run #16 到达 `REVIEW`。Code Review 和 Acceptance 的结构化结论均为 `passed: true`；Gate 退出码为 0，输出 `Ran 1 test ... OK`。
4. 审核的 diff 仅修改 `calculator.py`：`return a - b` 改为 `return a + b`。`changed_files` 只有该文件，`ready_to_merge` 为 `true`。
5. 审核前，本机测试仓库 `main` 为 `17be6ee61dfe9faa0868f885df6c97789475e75d`，工作树干净。调用网页同一条 `/api/runs/16/review` 审核接口批准后，Run 为 `SUCCEEDED`、`delivery_status=merged`；本机 `main` 为审核过的提交 `85588be867011e8ff8175d09daefd4900f814945`，工作树仍干净。远端 `data/worktrees/16` 已移除。

因此，**API 层面的 Mac → 远端 Herdr/Codex → Review → 本机合并 → worktree 清理闭环已跑通**。本次未通过浏览器手工点击审核按钮。

## 本次发现并修复

- Codex 首次启动时可能显示自动更新进度，然后退出要求重启。桥接程序现在等待已知更新画面，并在更新成功后重新启动一次；超时或其他未知提示仍报错。
- 系统创建的仓库克隆可能触发 Codex 信任提示。仅在 Full access、提示中的仓库路径与当前系统管理的 worktree 源克隆一致时继续；其他信任提示报错。此次首次提示针对已核实的一次性测试仓库，由操作者处理；自动处理路径尚未在全新仓库上单独验收。
- Codex 的终端会把一行 JSON 折成多行。桥接程序现在只取本轮带 nonce 的助手最终回答，并拼接其终端续行，避免把半行 JSON 交给 Code Review。

## 限制

- Herdr 保留运行中的终端，但当前桥接程序没有实现 Runner 或 Manager 崩溃后的自动恢复；不能据此声称持久执行或自动接管。
- `NEEDS_INPUT` 可保留 pane，完整的人机交互和恢复流程没有在本次验收。
- `PaseoDriver` 目前只经过命令构造的单元测试，没有进行真实远端任务、结构化输出或会话生命周期验收。
- 此次验证的是 Herdr 内的 Codex。Claude、AGY 等 Agent 未经过这条真实闭环验收。

## 复验入口

运行本地回归：`.venv/bin/python -m unittest discover -s tests -v`。在 Web 页面选已登记的 Project、`corp172-dev` Node 和 `herdr` Agent，提交仅改动一次性仓库的任务；到 Review 后核对 diff、Gate、Code Review、Acceptance，再点击 Approve。审核前后检查本机分支 HEAD，审核后检查远端 worktree 是否移除。
