"""集中构造故障分析模型的请求参数。

项目同时兼容 Chat Completions 与 Responses 两种 OpenAI 风格接口。本模块确保
文本、日志和图片分析使用相同模型，并统一启用可配置的深度推理强度。
"""


DEFAULT_AI_MODEL = "gpt-5.6-sol"
DEFAULT_REASONING_EFFORT = "high"


def build_ai_request_options(config, api_style):
    """根据接口风格返回模型与深度推理参数。

    推理强度配置为空时不发送额外字段，便于对接不支持推理参数的兼容接口。
    """
    options = {"model": config.get("OPENAI_MODEL", DEFAULT_AI_MODEL)}
    effort = str(
        config.get("OPENAI_REASONING_EFFORT", DEFAULT_REASONING_EFFORT) or ""
    ).strip().lower()
    if not effort:
        return options
    if str(api_style or "chat").lower() in ("response", "responses"):
        options["reasoning"] = {"effort": effort}
    else:
        options["reasoning_effort"] = effort
    return options
