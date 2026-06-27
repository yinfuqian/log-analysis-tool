import { ref, onMounted } from 'vue';
import ProductForm from '@/components/ProductForm.vue';
import productApi from '@/api/product';  
export default {
  components: { ProductForm },
  setup() {
    const products = ref([]); // 存储产品数据
    const showProductDialog = ref(false);
    const selectedProduct = ref(null);

    const fetchProducts = async () => {
    try {
      const data = await productApi.getProducts();  // 获取产品数据
      console.log('获取的产品数据:', data);
      if (Array.isArray(data.products)) {
        products.value = data.products;  // 从 data.products 中提取产品数组
      } else {
        console.error('返回的产品数据格式不正确:', data);
        products.value = [];  // 如果返回的数据不是数组，清空产品列表
      }
    } catch (error) {
      console.error('获取产品失败:', error);
    }
  };

    // 编辑产品
    const editProduct = async (product) => {
      try {
        selectedProduct.value = { ...product }; // 选择要编辑的产品
        showProductDialog.value = true;  // 显示弹窗
      } catch (error) {
        console.error('编辑产品失败:', error);
      }
    };

    // 保存产品信息
    const handleSaveProduct = async (productData) => {
      try {
        if (productData.id) {
          // 编辑产品
          const updatedProduct = await productApi.editProduct(productData);
          console.log('编辑成功:', updatedProduct);
        } else {
          // 创建新产品
          const newProduct = await productApi.addProduct(productData);
          console.log('创建成功:', newProduct);
        }
        fetchProducts(); // 重新加载产品列表
        showProductDialog.value = false;  // 关闭弹窗
      } catch (error) {
        console.error('保存产品失败:', error);
      }
    };


    // 删除产品
    const deleteProduct = async (productId) => {
      try {
        await productApi.deleteProduct(productId); // 直接传递 productId
        fetchProducts(); // 重新加载产品列表
        console.log(`删除成功: 产品 ID ${productId}`);
      } catch (error) {
        console.error('删除产品失败:', error);
      }
    };

    // 打开创建产品弹窗
    const openProductDialog = () => {
      selectedProduct.value = null; // 清空选中的产品
      showProductDialog.value = true;
    };

    // 监听弹窗关闭，重置表单
    const resetForm = () => {
      selectedProduct.value = null;
    };

    // 组件加载时获取产品数据
    onMounted(fetchProducts);

    return {
      products,
      showProductDialog,
      selectedProduct,
      openProductDialog,
      resetForm,
      editProduct,
      handleSaveProduct,
      deleteProduct
    };
  }
};