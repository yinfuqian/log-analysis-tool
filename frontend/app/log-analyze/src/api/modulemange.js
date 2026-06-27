import ModuleForm from '@/components/ModuleForm.vue';
import productApi from '@/api/product';  // 用于获取产品信息
import moduleApi from '@/api/module';  // 用于获取、删除、编辑、创建模块
import "@/assets/styles/module-manage.css";
export default {
  components: { ModuleForm },
  data() {
    return {
      products: [],  // 产品数据通过API获取
      modules: [],   // 模块数据通过API获取
      selectedProductId: null,
      showModuleDialog: false,
      selectedModule: {},
    };
  },
  watch: {
    selectedProductId(newVal) {
      if (newVal) {
        this.fetchModules();  // 选择产品后获取模块
      } else {
        this.modules = [];
      }
    }
  },
  methods: {
    // 获取产品数据
    async fetchProducts() {
      try {
        const data = await productApi.getProducts();
        console.log("API返回的产品数据：", data);
        this.products = data.products || [];  // 防止返回空产品数据时产生错误
      } catch (error) {
        console.error('获取产品数据失败:', error);
      }
    },

    onSelectProduct() {
      const product = this.products.find(item => item.id === this.selectedProductId);
      this.selectedModule = { ...this.selectedModule, product_name: product.name };
      this.fetchModules();
    },

    // 获取模块数据
    async fetchModules() { 
      try {
        if (this.selectedProductId) {
          const data = await moduleApi.getModulesByProduct(this.selectedProductId);
          console.log("API 返回的模块数据：", data);
          this.modules = (data.modules || []).map(module => ({
            id: module.module_id,  // 适配 ID 字段
            name: module.module_name,  // 适配名称字段
            branch: module.branch?.branch_address || '未知',  // 分支地址
            tag_version: module.branch?.tag_version || '未指定',  // 修正 tag_version
            product_name: this.products.find(product => product.id === this.selectedProductId)?.name || '未知产品'  // 获取产品名称
          }));
        }
      } catch (error) {
        console.error('获取模块数据失败:', error);
      }
    },

    // 删除模块
    async deleteModule(moduleId) {

      console.log("删除模块ID:", moduleId)
      try {
        await moduleApi.deleteModule(moduleId);
        this.fetchModules();  // 删除后刷新模块数据
      } catch (error) {
        console.error('删除模块失败:', error);
      }
    },


    // // 打开新增模块弹窗
    openModuleDialog() {
      this.selectedModule = { 
        id: null,  // 确保 ID 为空，防止误以为是更新
        name: '',
        branch: '',
        tag_version: '',
        product_name: this.products.find(product => product.id === this.selectedProductId)?.name || '',
      };
      console.log('selectedModule 新建时的数据：', this.selectedModule);
      this.showModuleDialog = true;
    },


    // 编辑模块
    editModule(module) {
      this.selectedModule = { 
        ...module, 
        product_name: module.product_name || '默认产品名称'  // 确保有产品名称
      };  
      console.log('selectedModule 编辑时的数据：', this.selectedModule);  // 打印值
      console.log('编辑模块时传递的 selectedModule:', this.selectedModule);
      this.showModuleDialog = true;
    },

    // 处理保存的模块
    handleSaveModule() {
      this.showModuleDialog = false;
      this.fetchModules(); // 只需要刷新模块数据，不需要再调用 API 了
    },

    // 重置表单
    resetForm() {
      this.selectedModule = null;
      this.showModuleDialog = false;
    }
  },

  // 页面加载时获取产品列表
  created() {
    this.fetchProducts();  // 页面加载时获取产品数据
  }
};