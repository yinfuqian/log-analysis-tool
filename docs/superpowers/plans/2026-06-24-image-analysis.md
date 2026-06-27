# 图片识别日志分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有日志分析系统新增图片识别输入能力，支持日志截图和业务截图，并复用当前代码分析主链路。

**Architecture:** 在后端新增独立图片上传入口，并在异步分析任务中基于 `source_type` 做文件/图片分流。Windows 客户端新增图片模式、标签选择、粘贴/拖拽/选图能力，结果仍通过现有结果弹窗展示。

**Tech Stack:** Flask, Celery, OpenAI Python SDK, Tkinter, Pillow, optional `windnd`

---

### Task 1: 后端图片上传入口

**Files:**
- Modify: `backend/tests/test_upload_processing_flow.py`
- Modify: `backend/app/logfile/routes/routes.py`

- [ ] 编写图片上传相关失败测试
- [ ] 实现图片文件校验、唯一命名和保存
- [ ] 返回统一上传结果结构

### Task 2: 后端异步分析图片分流

**Files:**
- Modify: `backend/tests/test_async_analysis_routes.py`
- Modify: `backend/app/analysis/routes/routes.py`
- Modify: `backend/app/analysis/routes/tasks.py`

- [ ] 编写 `submit_async` 图片模式校验测试
- [ ] 编写图片识别上下文构造测试
- [ ] 实现图片识别、上下文汇总和代码定位降级逻辑
- [ ] 让任务结果返回 `image_analysis`

### Task 3: 客户端图片模式与上传

**Files:**
- Modify: `windows-client/tests/test_api_client.py`
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/requirements.txt`

- [ ] 编写客户端图片模式与图片上传测试
- [ ] 实现模式切换、图片标签、图片描述、选图/粘贴/清空
- [ ] 实现图片上传 API 调用
- [ ] 接入拖拽支持

### Task 4: 结果展示与说明

**Files:**
- Modify: `windows-client/log_analyzer_client.py`

- [ ] 在结果摘要和弹窗中加入图片识别摘要
- [ ] 更新公告说明，提示支持图片识别输入

### Task 5: 验证

**Files:**
- Modify: `windows-client/build-exe.bat`

- [ ] 运行后端测试
- [ ] 运行客户端测试
- [ ] 如有需要更新打包依赖并验证 EXE 构建
