from flask import current_app as app
from app.utils.save_log_file import save_log_file
import os
import logging
import datetime
import re
from app.product.models.model import Product
from app.modules.models.model import Module
from app.branches.models.model import Branch

# 获取产品名称
def get_product_name_by_id(product_id):
    try:
        product = Product.query.get(product_id)
        app.logger.debug(f"从数据库获取产品: {product.name if product else '无'}")  # 调试日志
        return product.name if product else None
    except Exception as e:
        app.logger.error(f"获取产品名称失败: {str(e)}")
        return None


# 获取模块名称
def get_module_name_by_id(module_id):
    try:
        module = Module.query.get(module_id)
        app.logger.debug(f"从数据库获取模块: {module.name if module else '无'}")  # 调试日志
        return module.name if module else None
    except Exception as e:
        app.logger.error(f"获取模块名称失败: {str(e)}")
        return None

# 根据 `address` 和 `tag_version` 查询分支信息
def get_branch_address_by_name(address, tag_version):
    try:
        app.logger.debug(f"查询分支信息: address={address}, tag_version={tag_version}")  # 调试日志
        branch = Branch.query.filter_by(address=address, tag_version=tag_version).first()
        if branch:
            app.logger.debug(f"找到分支: {branch.address}, {branch.tag_version}")  # 调试日志
            return branch.address, branch.tag_version
        branch = Branch.query.filter_by(address=address).first()
        if branch:
            app.logger.debug(f"找到仓库地址，使用用户选择的远程分支: {branch.address}, {tag_version}")  # 调试日志
            return branch.address, tag_version
        app.logger.debug("没有找到匹配的分支")  # 调试日志
        return None, None
    except Exception as e:
        app.logger.error(f"获取分支信息失败: {str(e)}")
        return None, None

def remove_time_from_log(log_line):
    """ 移除日志中的时间字段，返回去除后的日志内容 """
    # 使用正则表达式匹配时间格式，假设时间字段为: yyyy-MM-dd HH:mm:ss.SSS
    log_line_without_time = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", "", log_line)
    return log_line_without_time # 

def process_log_file(log_lines):
    """ 处理日志文件，移除每行日志中的时间字段，并返回去除时间后的内容 """
    processed_lines = [remove_time_from_log(line) for line in log_lines]  # 处理每一行
    return processed_lines

def remove_duplicates(lines):
    seen = set()  # 使用集合来记录已出现过的日志
    unique_lines = []
    for line in lines:
        if line not in seen:
            seen.add(line)  # 添加到集合中
            unique_lines.append(line)  # 如果没有出现过，保留该行
    return unique_lines

def save_processed_log_file(lines, filename):
    """ 将处理后的日志行保存到新的文件 """
    save_dir = app.config.get('LOCAL_STORAGE_DIR', '/data/upload')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    app.logger.debug(f"保存处理后的日志文件到路径: {save_path}")  # 调试日志
    
   # 写入文件后再处理空行
    with open(save_path, 'w', encoding='utf-8') as new_log_file:
        # 先写入所有行
        for line in lines:
            new_log_file.write(line + "\n")
    
    # 重新读取文件并去除空行
    with open(save_path, 'r+', encoding='utf-8') as new_log_file:
        lines = new_log_file.readlines()  # 读取所有行
        new_log_file.seek(0)  # 将指针重置到文件开头
        new_log_file.truncate(0)  # 清空文件内容
        # 写入非空行
        for line in lines:
            if line.strip():  # 排除空行
                new_log_file.write(line)
    
    return save_path


def save_binary_upload_file(file_bytes, filename):
    save_dir = app.config.get('LOCAL_STORAGE_DIR', '/data/upload')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    app.logger.debug(f"保存二进制上传文件到路径: {save_path}")
    with open(save_path, 'wb') as file_obj:
        file_obj.write(file_bytes)
    return save_path

def sanitize_filename(filename):
    filename = re.sub(r'[\/:*?"<>|]', '_', filename)  # 替换非法字符
    return filename

def extract_error_logs(log_lines):
    error_logs = []
    for line in log_lines:
        if isinstance(line, bytes):
            line_str = line.decode('utf-8', errors='ignore')  # 将字节转换为字符串
        else:
            line_str = str(line)
        line_str = line_str.rstrip('\r\n')
        # 检查是否是非空行并且不包含 'INFO'
        if line_str.strip() and 'INFO' not in line_str:
            error_logs.append(line_str)
    return error_logs
