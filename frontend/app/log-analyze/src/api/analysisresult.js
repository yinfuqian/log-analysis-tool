import axios from 'axios';
import MarkdownViewer from '@/components/MarkdownViewer.vue';
import "@/assets/styles/analysis-result.css";

const VUE_APP_BASE_URL = process.env.VUE_APP_BASE_URL || 'http://localhost:5000';
const apiClient = axios.create({ baseURL: VUE_APP_BASE_URL });

export default {
  components: { MarkdownViewer },
  data() {
    return {
      productId: this.$route.query.product_id || null,
      moduleId: this.$route.query.module_id || null,
      branchAddress: this.$route.query.address || null,
      tagVersion: this.$route.query.tag_version || null,
      file_path: this.$route.query.file_path || null,
      repo_path: null,
      analysisResultRaw: '',
      analysisProgress: 0,
      analysisComplete: false,
      currentStatus: '开始分析...',
      dialogVisible: false,
      parsedLog: '',
      parsedCode: '',
      codeSnippets: []
    };
  },
  mounted() {
    this.startAnalysis();
  },
  methods: {
    async startAnalysis() {
      try {
        await this.pullCode();
        await this.parseLog();
        await this.showResult();
      } catch (error) {
        console.error("分析失败", error);
        this.currentStatus = '分析失败，请检查日志';
        this.analysisComplete = true;
        this.analysisProgress = 0;
      }
    },
    async pullCode() {
      this.currentStatus = '正在拉取代码...';
      this.analysisProgress = 20;
      const branchGetRes = await apiClient.post('/analysis/branch_get', {
        branchAddress: this.branchAddress,
        tagVersion: this.tagVersion
      });
      if (branchGetRes.data?.repo_path) {
        this.repo_path = branchGetRes.data.repo_path;
        this.currentStatus = '代码拉取成功';
        this.analysisProgress = 50;
      } else {
        throw new Error('未能获取 repo_path');
      }
    },
    async parseLog() {
      this.currentStatus = '正在解析日志...';
      this.analysisProgress = 65;
      const logRes = await apiClient.post('/analysis/log_analysis', {
        productId: this.productId,
        moduleId: this.moduleId,
        branchAddress: this.branchAddress,
        tagVersion: this.tagVersion,
        repo_path: this.repo_path,
        file_path: this.file_path
      });
      if (logRes.data?.log_analysis || logRes.data?.code_analysis) {
        this.analysisResultRaw = logRes.data;
        this.parsedLog = logRes.data.log_analysis || '';
        this.parsedCode = logRes.data.code_analysis || '';
        this.codeSnippets = logRes.data.code_snippets || [];
        this.currentStatus = '日志解析完成';
        this.analysisProgress = 80;
      } else {
        throw new Error('日志解析结果为空');
      }
    },
    async showResult() {
      this.currentStatus = '分析完成';
      this.analysisProgress = 100;
      this.analysisComplete = true;
      this.dialogVisible = true;
    },
    handleClose(done) {
      done();
    }
  }
};