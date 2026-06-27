<template>
  <div class="module-manage">
    <div class="top-bar">
      <el-select v-model="selectedProductId" placeholder="请选择产品" class="product-select" @change="onSelectProduct">
        <el-option v-for="product in products" :key="product.id" :label="product.name" :value="product.id" />
      </el-select>

      <el-button class="add-module-btn" type="primary" @click="openModuleDialog" :disabled="!selectedProductId">
        创建模块
      </el-button>
    </div>

    <!-- 模块表格 -->
    <el-table :data="modules" style="width: 100%" border class="module-table">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="模块名称" />
      <el-table-column prop="branch" label="代码分支" />
      <el-table-column prop="tag_version" label="分支版本" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <div  class="action-buttons">
            <el-button size="small" type="danger" @click="deleteModule(row.id)" class="delete-btn">删除</el-button>
            <el-button size="small" type="primary" @click="editModule(row)" class="edit-btn">编辑</el-button>

          </div>

        </template>
      </el-table-column>
    </el-table>

    <!-- 模块表单的弹窗 -->
    <el-dialog title="模块管理" v-model="showModuleDialog" @close="resetForm">
      <ModuleForm :module="selectedModule" @save="handleSaveModule" />
    </el-dialog>
  </div>
</template>

<script>
import modulemange  from '@/api/modulemange';
require('../assets/styles/module-manage.css')
export default modulemange
</script>
