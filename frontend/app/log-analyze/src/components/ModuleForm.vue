<template>
  <el-form :model="moduleForm" ref="moduleFormRef">
    <el-form-item label="模块名称">
      <el-input v-model="moduleForm.name" placeholder="请输入模块名称" />
    </el-form-item>

    <el-form-item label="分支地址">
      <el-input v-model="moduleForm.branch" placeholder="请输入分支地址" />
    </el-form-item>

    <el-form-item label="分支版本">
      <el-input v-model="moduleForm.tag_version" placeholder="请输入分支版本" />
    </el-form-item>

    <!-- 产品名称只显示，不能编辑 -->
    <el-form-item label="产品名称">
      <el-input :value="moduleForm.product_name" placeholder="产品名称" readonly />
    </el-form-item>

    <el-footer>
      <el-button @click="handleSave" type="primary">保存</el-button>
    </el-footer>
  </el-form>
</template>

<script>
import moduleApi from '@/api/module'; // 导入 moduleApi
export default {
  props: {
    module: Object,  // 通过 props 接收父组件传递的 module 数据
  },
  data() {  
    return {
      moduleForm: {}
    };
  },
  watch: {
    module: {
      handler() {
        this.initModuleForm();
      },
      immediate: true,
    }
  },
  methods: {
    initModuleForm() {
      this.moduleForm = {
        id: this.module ? this.module.id : '',
        name: this.module ? this.module.name : '',
        branch: this.module ? this.module.branch : '',
        tag_version: this.module ? this.module.tag_version : '',
        product_name: this.module ? this.module.product_name : ''
      }
    },
    // 保存模块
    async handleSave() {
      try {
        if (this.moduleForm.id) {
          // 编辑模块，直接调用 editModule
          await moduleApi.editModule(this.moduleForm);
        } else {
          // 如果没有传递module，表示是新建模块
          await moduleApi.addModule(this.moduleForm);
        }
        // 保存成功后通知父组件关闭弹窗
        this.$emit('save'); 
      } catch (error) {
        console.error('保存模块失败:', error);
      }
    }
  }
};
</script>
