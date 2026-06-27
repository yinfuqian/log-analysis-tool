<template>
  <div class="dashboard">
    <el-row class="stats-row">
      <el-col :span="8" class="stat-card">
        <div class="stat-card-content">
          <h3>上传文件数量</h3>
          <p>{{ uploadedFiles }}</p>
        </div>
      </el-col>
      <el-col :span="8" class="stat-card">
        <div class="stat-card-content">
          <h3>分析成功次数</h3>
          <p>{{ successfulAnalyses }}</p>
        </div>
      </el-col>
      <el-col :span="8" class="stat-card">
        <div class="stat-card-content">
          <h3>产品概览</h3>
          <p>{{ productCount }}</p>
        </div>
      </el-col>
      <el-col :span="8" class="stat-card">
        <div class="stat-card-content">
          <h3>分析失败次数</h3>
          <p>{{ failedAnalyses }}</p>
        </div>
      </el-col>
      <!-- 仓库存量 -->
      <el-col :span="8" class="stat-card">
        <div class="stat-card-content">
          <h3>仓库存量</h3>
          <p>{{ stockCount }}</p>
        </div>
      </el-col>
    </el-row> 
  </div>
</template>

<script>
import logdashbord from '@/api/logdashbord';
import "@/assets/styles/log-dashboard.css";
export default {
  data() {
    return {
      uploadedFiles: 0,
      successfulAnalyses: 0,
      productCount: 0,
      failedAnalyses: 0,
      stockCount: 0
    };
  },
  created() {
    this.fetchDashboardData();
  },
  methods: {
    async fetchDashboardData() {
      try {
        const response = await logdashbord.getDashboardData();
        this.uploadedFiles = response.uploadedFiles || 0;
        this.successfulAnalyses = response.successfulAnalyses || 0;
        this.productCount = response.productCount || 0;
        this.failedAnalyses = response.failedAnalyses || 0;
        this.stockCount = response.stockCount || 0;
      } catch (error) {
        console.error('获取dashboar 数据失败:', error);
      }
    }
  }
};
</script>
