
def build_gpt_prompt(log_content, code_snippets=None):
    """
    构造给 GPT 的 prompt
    """
    base_prompt = "你是一个专业的日志分析助手，请帮我分析日志中可能存在的错误、异常及根因。"

    if code_snippets:
        prompt = (
            f"{base_prompt}\n\n"
            f"以下是日志内容：\n{log_content}\n\n"
            f"以下是日志中涉及的代码片段：\n{code_snippets}"
        )
    else:
        prompt = f"{base_prompt}\n\n日志如下：\n{log_content}"

    return prompt
