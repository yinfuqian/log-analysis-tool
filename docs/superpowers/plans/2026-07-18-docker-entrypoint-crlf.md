# Docker Entrypoint CRLF Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保证后端镜像在 Windows 工作区和其他可能包含 CRLF 的构建上下文中都能正常执行 `/app/docker-entrypoint.sh`。

**Architecture:** 仓库层使用 `.gitattributes` 固定 Shell 脚本为 LF，镜像层在 `COPY . .` 后再次清除所有 `.sh` 文件的回车字符。合同测试同时约束两层保护，真实 Docker 构建和默认 ENTRYPOINT 启动作为最终验收。

**Tech Stack:** Git attributes、Dockerfile、POSIX `find`/`sed`、Python `unittest`、Docker Compose。

---

### Task 1: 添加失败的行尾保护合同测试

**Files:**
- Modify: `backend/tests/test_docker_contract.py`

- [ ] **Step 1: 添加仓库和镜像双重保护测试**

```python
def test_backend_shell_scripts_are_normalized_for_linux(self):
    dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    self.assertIn("*.sh text eol=lf", attributes)
    self.assertIn("find /app -type f -name '*.sh' -exec sed -i 's/\\r$//' {} +", dockerfile)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_docker_contract.DockerContractTests.test_backend_shell_scripts_are_normalized_for_linux -v
```

Expected: FAIL，缺少 `*.sh text eol=lf` 或 Dockerfile 的 CRLF 转换命令。

### Task 2: 实现仓库和镜像双重保护

**Files:**
- Modify: `.gitattributes`
- Modify: `backend/Dockerfile`

- [ ] **Step 1: 在 `.gitattributes` 中固定 Shell 脚本行尾**

```gitattributes
*.sh text eol=lf
```

- [ ] **Step 2: 在 Dockerfile 复制源码后转换所有 Shell 脚本**

将构建准备命令改为：

```dockerfile
RUN find /app -type f -name '*.sh' -exec sed -i 's/\r$//' {} + \
    && chmod +x /app/docker-entrypoint.sh /app/migrate_db.sh /app/start.sh /app/start_worker.sh \
```

- [ ] **Step 3: 运行合同测试并确认通过**

Run:

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_docker_contract -v
```

Expected: 7 项测试通过。

### Task 3: 构建并验证真实镜像

**Files:**
- Verify: `backend/Dockerfile`
- Verify: `backend/docker-entrypoint.sh`

- [ ] **Step 1: 构建修复镜像**

```powershell
docker build --build-arg PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim-bookworm -t fault-analysis-backend:crlf-fix backend
```

Expected: 构建退出码 0，运行时和 OCR 构建检查通过。

- [ ] **Step 2: 使用默认 ENTRYPOINT 启动镜像**

```powershell
docker run --rm fault-analysis-backend:crlf-fix sh -c "printf ENTRYPOINT_OK"
```

Expected: 输出 `ENTRYPOINT_OK`，不再出现 `no such file or directory`。

- [ ] **Step 3: 检查镜像内脚本行尾**

```powershell
docker run --rm --entrypoint /bin/sh fault-analysis-backend:crlf-fix -c "if grep -U `$'\\r' /app/docker-entrypoint.sh; then exit 1; fi"
```

Expected: 退出码 0。

### Task 4: 回归并提交

**Files:**
- Verify: `.gitattributes`
- Verify: `backend/Dockerfile`
- Verify: `backend/tests/test_docker_contract.py`

- [ ] **Step 1: 运行注释、差异和 Compose 检查**

```powershell
python scripts\check_source_comments.py
git diff --check
docker compose config --quiet
```

Expected: 所有命令退出码为 0。

- [ ] **Step 2: 提交修复**

```powershell
git add .gitattributes backend/Dockerfile backend/tests/test_docker_contract.py docs/superpowers/plans/2026-07-18-docker-entrypoint-crlf.md
git commit -m "fix: normalize docker entrypoint line endings"
```
