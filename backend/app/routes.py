from flask import Blueprint, jsonify
from app.product.models.model import Product # 产品信息
from app.branches.models.model  import Branch  # 分支数量
from app.logfile.models.model import Log, QueryRecord # 文件数量，访问成功失败次数
dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/get', methods=['GET'])
def get_dashboard_data():
    # 获取上传的文件数量
    uploaded_files = Log.query.count()
    
    # 获取分析成功次数和分析失败次数
    successful_analyses = QueryRecord.query.filter(QueryRecord.answer == 0).count()
    failed_analyses = QueryRecord.query.filter(QueryRecord.answer == 1).count()
    
    # 获取产品数量
    product_count = Product.query.count()
    
    # 获取仓库存量，这里可以根据你的数据表设计来调整
    stock_count = Branch.query.count()  # 假设仓库存量基于分支数量

    # 返回 JSON 格式的响应
    return jsonify({
        'uploadedFiles': uploaded_files,
        'successfulAnalyses': successful_analyses,
        'failedAnalyses': failed_analyses,
        'productCount': product_count,
        'stockCount': stock_count
    })
