<template>
  <div class="product-form">
    <el-form @submit.prevent="handleSubmit" label-width="80px" class="form-container">
      <!-- 产品名称输入框 -->
      <el-form-item label="产品名称" prop="name">
        <el-input v-model="localProduct.name" placeholder="请输入产品名称" />
      </el-form-item>

      <!-- 保存按钮 -->
      <el-form-item>
        <el-button type="primary" native-type="submit">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script>
import "@/assets/styles/product-form.css";
export default {
  props: {
    product: Object, // 父组件传递的产品数据
  },
  data() {
    return {
      // 使用本地副本来存储和修改产品数据
      localProduct: { ...this.product }
    };
  },
  methods: {
    handleSubmit() {
      console.log("保存的产品数据:", this.localProduct);
      this.$emit('save', this.localProduct); // 通过事件传递修改后的产品数据
    }
  },
  watch: {
    // 当父组件传入的 product 发生变化时，更新本地副本
    product(newProduct) {
      this.localProduct = { ...newProduct };
    }
  }
};
</script>
