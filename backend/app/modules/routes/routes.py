import subprocess
import logging
from flask import Blueprint, request, jsonify, current_app as app
from extensions import db
from ..models import Module
from ...product.models import Product
from ...branches.models.model import Branch
from ...relasionship.models.model import ProductModule, ModuleBranch
from urllib.parse import urlparse
from datetime import datetime

module_bp = Blueprint('module', __name__)

# 配置日志格式
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@module_bp.route('/get', methods=['GET'])
def get_product_modules():
    """获取指定产品的所有模块及其对应的分支信息"""
    product_id = request.args.get('product_id')
    
    if not product_id:
        app.logger.warning("请求缺少 product_id 参数")
        return jsonify({"error": "缺少 product_id 参数"}), 400

    app.logger.info(f"收到获取产品模块请求，product_id: {product_id}")

    # 检查产品是否存在
    product = Product.query.get(product_id)
    if not product:
        app.logger.warning(f"产品 ID {product_id} 不存在")
        return jsonify({"error": "产品不存在"}), 404

    # 获取产品关联的所有模块
    product_modules = ProductModule.query.filter_by(product_id=product_id).all()
    
    if not product_modules:
        app.logger.info(f"产品 ID {product_id} 没有关联的模块")
        return jsonify({"product_id": product_id, "modules": []}), 200

    modules_data = []
    
    for pm in product_modules:
        module = Module.query.get(pm.module_id)
        if not module:
            app.logger.warning(f"模块 ID {pm.module_id} 不存在，跳过")
            continue  # 如果模块不存在，跳过

        # 获取模块的分支信息（一个模块只有一个分支）
        module_branch = ModuleBranch.query.filter_by(module_id=module.id).first()
        
        branch_info = None
        if module_branch:
            branch = Branch.query.get(module_branch.branch_id)
            if branch:
                branch_info = {
                    "branch_address": branch.address,
                    "tag_version": branch.tag_version
                }
                app.logger.info(f"模块 ID {module.id} 关联分支: {branch_info}")

        # 构造模块信息
        module_data = {
            "module_id": module.id,
            "module_name": module.name,
            "branch": branch_info  # 可能为 None
        }
        modules_data.append(module_data)

    app.logger.info(f"产品 ID {product_id} 的模块数据: {modules_data}")

    return jsonify({"product_id": product_id, "modules": modules_data}), 200



# 创建模块（可选关联产品）
@module_bp.route('/add', methods=['POST'])
def create_module():
    try:
        data = request.json
        name = data.get('name')
        product_name = data.get('product_name')  # 关联的产品名称
        branch_address = data.get('branch')  # 传入的 Git 仓库地址
        tag_version = data.get('tag_version')  # 传入的 Git 分支版本

        # 检查必填参数
        if not name or not branch_address or not tag_version:
            app.logger.error('模块名称、Git仓库地址和版本不能为空')
            return jsonify({'message': '模块名称、Git仓库地址和版本不能为空'}), 400

        # 检查 Branch 是否已经存在
        branch = Branch.query.filter_by(address=branch_address, tag_version=tag_version).first()
        if not branch:
            # 创建新的分支记录
            branch = Branch(address=branch_address, tag_version=tag_version)
            db.session.add(branch)
            db.session.commit()
            app.logger.info(f"Git 仓库地址 '{branch_address}' 和版本 '{tag_version}' 创建成功")
        else:
            app.logger.info(f"Git 仓库地址 '{branch_address}' 和版本 '{tag_version}' 已存在，ID: {branch.id}")  
        
        # 获取所有已关联的模块
        module_branch = ModuleBranch.query.filter_by(branch_id=branch.id).all()
        
        # 查找模块名称是否已存在
        existing_module = None
        for module_relation in module_branch:
            module = Module.query.filter_by(id=module_relation.module_id).first()
            if module and module.name == name:
                existing_module = module
                break
        
        if existing_module:
            app.logger.info(f"模块 '{name}' 已存在，ID: {existing_module.id}, Git 地址: {branch.address}, Tag 版本: {branch.tag_version}")
            return jsonify({
                'message': '模块已存在',
                'module_id': existing_module.id,
                'git_address': branch.address,
                'tag_version': branch.tag_version
            }), 400
        
        # **创建新模块**
        module = Module(name=name)
        db.session.add(module)
        db.session.commit()
        app.logger.info(f"模块 '{name}' 创建成功，ID: {module.id}")

        # **创建模块和分支的关联**
        existing_association = ModuleBranch.query.filter_by(module_id=module.id, branch_id=branch.id).first()
        if not existing_association:
            module_branch = ModuleBranch(module_id=module.id, branch_id=branch.id)
            db.session.add(module_branch)
            db.session.commit()
            app.logger.info(f"模块 '{module.id}' 关联分支 '{branch.id}' 成功")

        # **查找产品**
        product = Product.query.filter_by(name=product_name).first()
        if product:
            existing_product_association = ProductModule.query.filter_by(product_id=product.id, module_id=module.id).first()
            if not existing_product_association:
                product_module = ProductModule(product_id=product.id, module_id=module.id)
                db.session.add(product_module)
                db.session.commit()
                app.logger.info(f"模块 '{module.id}' 关联产品 '{product.id}' 成功")
        else:
            app.logger.error(f"无效的产品名称,或者不存在，请先确定产品存在 {product_name}")
            return jsonify({'message': '无效的产品名称,或者不存在，请先确定产品存在'}), 400

        # **确保成功创建后返回响应**
        return jsonify({'message': '模块创建成功', 'module_id': module.id}), 201

    except Exception as e:
        app.logger.error(f"创建模块时发生错误: {str(e)}")
        return jsonify({'message': '服务器内部错误', 'error': str(e)}), 500  # 返回 500 状态码，包含错误信息



def check_git_permission(branch_address, git_username, git_password):
    try:
        # 解析 URL 来提取仓库的域名和路径
        parsed_url = urlparse(branch_address)
        
        # 确保 URL 没有重复的 https:// 前缀
        if parsed_url.scheme != 'https':
            raise ValueError(f"Git 地址必须是以 https:// 开头，当前地址: {branch_address}")

        # 去除完整 URL 的 https://，只留下域名和路径
        base_url = f"{parsed_url.netloc}{parsed_url.path}"

        # 构造带有凭证的 Git 仓库 URL
        command = [
            'git', 'ls-remote',  # 使用 ls-remote 命令检查远程仓库
            f'https://{git_username}:{git_password}@{base_url}'
        ]

        # 执行 git 命令
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # 检查命令执行结果
        if result.returncode == 0:
            # 如果返回码为 0，说明有权限
            app.logger.info(f"Git 用户 '{git_username}' 成功验证权限，能拉取仓库 '{branch_address}'")
            return True
        else:
            # 如果返回码不为 0，说明没有权限
            app.logger.error(f"Git 用户 '{git_username}' 权限验证失败，仓库地址: {branch_address}，错误信息: {result.stderr}")
            return False
    except subprocess.CalledProcessError as e:
        # 如果执行命令时出错
        app.logger.error(f"Git 权限验证过程中出现错误: {e}")
        return False
    except Exception as e:
        # 捕获其他异常
        app.logger.error(f"请求错误: {e}")
        return False


# 删除模块及关联记录
@module_bp.route('/delete', methods=['POST'])
def delete_module():
    data = request.json
    module_id = data.get('module_id')

    # 检查模块ID是否提供
    if not module_id:
        app.logger.error('模块ID不能为空')
        return jsonify({'message': '模块ID不能为空'}), 400

    # 查找模块是否存在
    module = Module.query.get(module_id)
    if not module:
        app.logger.error(f"模块ID '{module_id}' 不存在")
        return jsonify({'message': f"模块ID '{module_id}' 不存在"}), 404

    # 删除与模块关联的所有 ModuleBranch 记录（即模块与分支的关联）
    module_branches = ModuleBranch.query.filter_by(module_id=module.id).all()
    for module_branch in module_branches:
        db.session.delete(module_branch)
        app.logger.info(f"已删除模块 '{module.id}' 与分支 '{module_branch.branch_id}' 的关联")

    # 删除与模块关联的所有 ProductModule 记录（即模块与产品的关联）
    product_modules = ProductModule.query.filter_by(module_id=module.id).all()
    for product_module in product_modules:
        db.session.delete(product_module)
        app.logger.info(f"已删除模块 '{module.id}' 与产品 '{product_module.product_id}' 的关联")

    # 删除模块记录
    db.session.delete(module)
    db.session.commit()

    app.logger.info(f"模块 '{module.id}' 删除成功")
    return jsonify({'message': '模块及其关联记录删除成功'}), 200


## 更新模块
@module_bp.route('/update', methods=['POST'])
def update_module():
    try:
        data = request.json
        module_id = data.get('id')
        product_name = data.get('product_name')
        new_name = data.get('name')
        new_branch_address = data.get('branch')
        new_tag_version = data.get('tag_version')

        if not module_id:
            app.logger.error('模块ID不能为空')
            return jsonify({'message': '模块ID不能为空'}), 400

        if not product_name:
            app.logger.error('产品名称不能为空')
            return jsonify({'message': '产品名称不能为空'}), 400

        if not new_name:
            app.logger.error('新名称不能为空')
            return jsonify({'message': '新名称不能为空'}), 400

        module = Module.query.get(module_id)
        if not module:
            app.logger.error(f"模块ID '{module_id}' 不存在")
            return jsonify({'message': f"模块ID '{module_id}' 不存在"}), 404

        product = Product.query.filter_by(name=product_name).first()
        if not product:
            app.logger.error(f"产品 '{product_name}' 不存在")
            return jsonify({'message': f"产品 '{product_name}' 不存在"}), 404

        product_module = ProductModule.query.filter_by(product_id=product.id, module_id=module.id).first()
        if not product_module:
            app.logger.error(f"产品 '{product_name}' 下没有模块 '{module_id}'")
            return jsonify({'message': f"产品 '{product_name}' 下没有模块 '{module_id}'"}), 400

        if new_name and new_name.strip():
            module.name = new_name
            db.session.commit()
            app.logger.info(f"模块 '{module.id}' 名称更新为 '{new_name}'")

        module_branch = ModuleBranch.query.filter_by(module_id=module.id).first()
        current_branch = Branch.query.get(module_branch.branch_id) if module_branch else None
        current_tag_version = current_branch.tag_version if current_branch else None

        new_branch_address = new_branch_address or (current_branch.address if current_branch else None)
        new_tag_version = new_tag_version or current_tag_version

        if new_branch_address and new_tag_version:
            if current_branch and current_branch.address == new_branch_address and current_tag_version == new_tag_version:
                app.logger.info(f"模块 '{module.id}' 的分支和版本号未变更")
            else:
                branch = Branch.query.filter_by(address=new_branch_address).first()
                if not branch:
                    branch = Branch(address=new_branch_address, tag_version=new_tag_version)
                    db.session.add(branch)
                    db.session.commit()
                    app.logger.info(f"新 Git 分支 '{new_branch_address}'（版本: {new_tag_version}）创建成功")
                elif branch.tag_version != new_tag_version:
                    branch.tag_version = new_tag_version
                    branch.updated_at = datetime.utcnow()
                    db.session.commit()
                    app.logger.info(f"更新分支 '{new_branch_address}' 版本号到 '{new_tag_version}'")

                if module_branch and current_branch.address != new_branch_address:
                    db.session.delete(module_branch)
                    db.session.commit()
                    app.logger.info(f"移除模块 '{module.id}' 旧的分支 '{current_branch.address}' 关联")

                new_module_branch = ModuleBranch(module_id=module.id, branch_id=branch.id)
                db.session.add(new_module_branch)
                db.session.commit()
                app.logger.info(f"模块 '{module.id}' 关联新分支 '{branch.address}'（版本: {branch.tag_version}）成功")

        return jsonify({'message': '模块更新成功', 'module_id': module.id}), 200
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"更新模块时发生错误: {str(e)}")
        return jsonify({'message': '模块更新失败', 'error': str(e)}), 500
