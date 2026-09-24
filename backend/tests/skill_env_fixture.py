"""技能运行参数的测试夹具。

服务端配置是技能运行参数的唯一来源（见 app/skillrun/env_lock.py），缺少必填项时任务会被直接拒绝。
测试不能依赖开发者本机的 .env，因此统一用这里的一组测试值构造应用配置。
"""

# 与 .env 中七项运行参数对应的测试值；令牌都是假值，不会访问真实 Jira。
LOCKED_SKILL_ENV = {
    "JIRA_BASE_URL": "https://jira.example.com",
    "JIRA_TOKEN": "jira-token-from-env",
    "DEVOPS_MCP_URL": "https://devops.example.com/mcp",
    "DEVOPS_MCP_TOKEN": "devops-token-from-env",
    "CODEX_MODEL": "codex/test-model",
    "CODEX_MODEL_PROVIDER": "testprovider",
    "CODEX_BASE_URL": "https://model.example.com/v1",
}


def with_locked_skill_env(config: dict) -> dict:
    """把测试值合并进应用配置；调用方传入的值优先，便于用例覆盖单项。"""
    merged = dict(LOCKED_SKILL_ENV)
    merged.update(config or {})
    return merged
