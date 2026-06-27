import productApi from '@/api/product';
import moduleApi from '@/api/module';
import axios from "axios";

const VUE_APP_BASE_URL = process.env.VUE_APP_BASE_URL || "http://localhost:5000";

export default {
  data() {
    return {
      products: [],
      modules: [],
      branches: [],
      selectedProduct: null,
      selectedModule: null,
      selectedBranch: null,
      selectedBranchVersion: null,
      fileList: [],
      uploadUrl: `${VUE_APP_BASE_URL}/logfile/upload`,
    };
  },

  computed: {
    // 根据 `selectedBranch` 过滤出对应的 `branchVersions`
    filteredBranchVersions() {
      const selectedBranchObj = this.branches.find(b => b.address === this.selectedBranch);
      return selectedBranchObj ? selectedBranchObj.versions : [];
    },

    // 上传时附带的参数
    uploadParams() {
      return {
        product_id: this.selectedProduct,
        module_id: this.selectedModule,
        address: this.selectedBranch,
        tag_version: this.selectedBranchVersion
      };
    },
  },

  methods: {
    async fetchProducts() {
      try {
        console.log("获取 products...");
        const data = await productApi.getProducts();
        this.products = data.products || [];

        if (this.selectedProduct) {
          this.fetchModules();
        }
      } catch (error) {
        console.error("获取产品失败:", error);
      }
    },

    async fetchModules() {
      if (!this.selectedProduct) return;
      try {
        console.log(`获取模块、分支和版本信息: ${this.selectedProduct}`);
        const data = await moduleApi.getModulesByProduct(this.selectedProduct);

        this.modules = data.modules || [];
        this.selectedModule = null;
        this.selectedBranch = null;
        this.selectedBranchVersion = null;
        this.branches = [];

        // 整理分支和对应的版本
        const branchMap = {};
        this.modules.forEach(module => {
          if (module.branch) {
            const { branch_address, tag_version } = module.branch;
            if (!branchMap[branch_address]) {
              branchMap[branch_address] = new Set();
            }
            branchMap[branch_address].add(tag_version);
          }
        });

        // 转换为数组格式 [{ address: "branch1", versions: ["v1", "v2"] }]
        this.branches = Object.entries(branchMap).map(([address, versions]) => ({
          address,
          versions: Array.from(versions)
        }));

      } catch (error) {
        console.error("获取模块、分支和版本数据失败:", error);
      }
    },

    onProductChange() {
      this.fetchModules();
    },

    // 选择分支时，更新 `selectedBranchVersion`
    onBranchChange() {
      this.selectedBranchVersion = null; // 重置版本选择
    },

    beforeUpload(file) {
      if (!this.selectedProduct || !this.selectedModule || !this.selectedBranch || !this.selectedBranchVersion) {
        this.$message.error("请先选择产品、模块、分支地址和分支版本");
        return false;
      }
      return true;
    },

    onUploadSuccess(response) {
      console.log("上传成功:", response);
      if (response.message === "文件上传并处理成功") {
        this.$message.success("日志上传成功！");

        // 传递所有表单数据
        this.$router.push({
          name: "AnalysisResult",
          query: {
            product_id: this.selectedProduct,
            module_id: this.selectedModule,
            address: this.selectedBranch,
            tag_version: this.selectedBranchVersion,
            file_path: response.file_path
          },
        });
      } else {
        this.$message.error(response.error || "上传失败");
      }
    },

    onUploadError(error) {
      console.error("上传失败:", error);
      this.$message.error("上传失败，请检查网络或联系管理员");
    },
  },

  mounted() {
    this.fetchProducts();
  },
};