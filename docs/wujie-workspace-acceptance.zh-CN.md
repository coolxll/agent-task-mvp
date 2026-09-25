# wujie 开发工作区验收（2026-09-26）

## 已准备

- 主机：`wujie`（远端主机名 `SH-4631`）。
- 项目目录：`/home/coolx/workspace/personal/agent-task-mvp`，从 GitHub `main` 检出；初始检出 HEAD 为 `f859cd848af1830bdf0c6986726b9a18b8028974`，此后通过 `git pull --ff-only` 同步。
- Python：系统 `/usr/bin/python3` 为 3.12.3；使用 `/home/coolx/.local/bin/uv` 创建项目内 `.venv`，依照 `requirements.txt` 安装依赖。没有把依赖安装到系统 Python。
- Git：提交身份已配置；项目局部 `core.autocrlf=input`，检出文件为 LF，工作树干净。
- 验证：`.venv/bin/python -m unittest discover -s tests -v`，38 项通过。

继续开发：

```bash
ssh wujie
cd ~/workspace/personal/agent-task-mvp
source .venv/bin/activate
git pull --ff-only
python -m unittest discover -s tests -v
```

## 当前边界

此工作区用于编辑代码和运行 Python 测试。`wujie` 当前 PATH 中没有 `node`、`npm`、`codex`、`claude`、`agy`、`pi` 或 `herdr`；本次没有配置 Runner 服务、Node 注册、Agent 登录态或远端任务执行。因此不能把这个工作区视为已接入 Manager 的执行节点。若需要在 `wujie` 上运行 Agent，需另行安装对应运行时并做真实任务验收。
