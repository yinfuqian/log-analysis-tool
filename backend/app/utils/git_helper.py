# app/utils/git_helper.py
import os
import subprocess

def clone_git_repo(repo_url, target_dir, tag=None):
    """
    克隆 Git 仓库到指定目录，并切换到 tag（如果提供）
    """
    if os.path.exists(target_dir):
        subprocess.run(["rm", "-rf", target_dir])
    subprocess.run(["git", "clone", repo_url, target_dir])
    if tag:
        subprocess.run(["git", "checkout", tag], cwd=target_dir)
        
        

def get_code_snippet(base_dir, class_path, line_number, context=5):
    """
    从 class_path 获取代码片段，返回上下文代码（前后若干行）
    """
    file_path = os.path.join(base_dir, *class_path.split(".")) + ".java"
    if not os.path.exists(file_path):
        return f"未找到代码文件：{file_path}"

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start = max(0, line_number - context - 1)
    end = min(len(lines), line_number + context)

    snippet = "".join(lines[start:end])
    return f"{file_path} (line {line_number}):\n{snippet}"
