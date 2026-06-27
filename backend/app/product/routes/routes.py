from flask import Blueprint, request, jsonify, current_app as app
from app.product.models import Product
from extensions import db
product_bp = Blueprint('product', __name__)

# 创建产品
@product_bp.route('/add', methods=['POST'])
def create_product():
    data = request.get_json()

    # 获取请求数据
    name = data.get('name')
    description = data.get('description')

    if not name:
        app.logger.warning("创建产品失败：产品名称是必填项")
        return jsonify({"error": "产品名称是必填项"}), 400
    
    
    # 判断是否已经存在同样名称的产品
    existing_product = Product.query.filter_by(name=name).first()
    if existing_product:
        app.logger.warning(f"创建产品失败：产品名称 '{name}' 已存在")
        return jsonify({"error": f"产品名称 '{name}' 已存在"}), 400

    # 创建新产品
    new_product = Product(
        name=name,
        description=description
    )

    db.session.add(new_product)
    db.session.commit()

    # 记录创建成功的日志
    app.logger.info(f"创建产品成功：ID {new_product.id}，名称 {new_product.name}")

    return jsonify({"message": "产品创建成功", "product_id": new_product.id}), 201

# 获取所有产品或根据名称过滤获取产品
@product_bp.route('/get', methods=['GET'])  # 相对路径，/product/
def get_products():
    product_name = request.args.get('name')  # 获取查询参数中的name

    if product_name:
        # 根据产品名称过滤产品
        products = Product.query.filter(Product.name.like(f'%{product_name}%')).all()
        app.logger.info(f"根据名称过滤获取产品信息成功：名称包含 '{product_name}'")
    else:
        # 获取所有产品
        products = Product.query.all()
        app.logger.info("获取所有产品信息成功")

    # 返回产品信息
    product_list = [{"id": p.id, "name": p.name, "description": p.description} for p in products]
    return jsonify({"products": product_list})


# 修改产品
@product_bp.route('/edit', methods=['POST'])
def update_product():
    data = request.get_json()
    product_id = data.get('id')
    product = Product.query.get_or_404(product_id)

    # 获取更新后的产品名称
    new_name = data.get('name')
    
        # 判断是否有其他产品使用相同名称
    if new_name:
        existing_product = Product.query.filter_by(name=new_name).first()
        if existing_product and existing_product.id != product.id:
            app.logger.warning(f"更新产品失败：已存在同名产品，名称 '{new_name}'")
            return jsonify({"error": f"已存在同名产品，名称 '{new_name}'"}), 400
    
    # 更新数据
    product.name = data.get('name', product.name)
    product.description = data.get('description', product.description)
    

    db.session.commit()

    app.logger.info(f"更新产品信息成功：ID {product_id}，新名称 {product.name}")

    return jsonify({"message": "产品信息更新成功"})

# 删除指定产品
@product_bp.route('/delete', methods=['POST'])
def delete_product():
    data = request.get_json()
    product_id = data.get('id')
    product = Product.query.get_or_404(product_id)

    db.session.delete(product)
    db.session.commit()

    app.logger.info(f"删除产品成功：ID {product_id}，名称 {product.name}")

    return jsonify({"message": "产品删除成功"})
