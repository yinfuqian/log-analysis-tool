<template>
  <div class="system-manage">
    <el-card>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="产品管理" name="product">
          <ProductManage />
        </el-tab-pane>
        <el-tab-pane label="产品模块管理" name="module">
          <ModuleManage />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script>
import systemmange from '@/api/systemmange';
export default systemmange
</script>
