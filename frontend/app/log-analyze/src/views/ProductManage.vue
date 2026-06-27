<template>
  
  <div class="product-manage">
    <!-- 创建产品按钮 -->
    <el-button class="add-product-btn" type="primary" @click="openProductDialog">
      创建产品
    </el-button>

    <!-- 产品表格 -->
    <el-table :data="products" style="width: 100%" border class="product-table">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="产品名称" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <div class="action-buttons">
            <el-button size="small" type="danger" @click="deleteProduct(row.id)" class="delete-btn">删除</el-button>
            <el-button size="small" type="primary" @click="editProduct(row)" class="edit-btn">编辑</el-button>
          </div>
        </template>
      </el-table-column>

    </el-table>

    <!-- 产品表单组件的弹窗 -->
    <el-dialog title="创建产品" v-model="showProductDialog" @close="resetForm">
      <ProductForm :product="selectedProduct" @save="handleSaveProduct" />
    </el-dialog>
  </div>
</template>

<script>
import productmanage from '@/api/productmanage';
require('../assets/styles/product-manage.css');
export default productmanage
</script>


