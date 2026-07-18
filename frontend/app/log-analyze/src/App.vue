<template>
  <div id="app">
    <router-view v-if="$route.name === 'Login'"></router-view>
    <el-container v-else>
      <!-- 侧边栏 -->
      <el-aside width="200px" class="sidebar">
        <el-menu :default-active="$route.path" router>
          <!-- 首页 -->
          <el-menu-item index="/">
            <el-icon><HomeFilled /></el-icon>
            <span>首页</span>
          </el-menu-item>
          <!-- 上传日志 -->
          <el-menu-item index="/upload">
            <el-icon><UploadFilled /></el-icon>
            <span>上传故障资料</span>
          </el-menu-item>
          <!-- 分析结果 -->
          <el-menu-item index="/analysisresult">
            <el-icon><Document /></el-icon>
            <span>分析结果</span>
          </el-menu-item>
          <!-- 系统管理 -->
          <el-menu-item index="/systemmanage">
            <el-icon><Document /></el-icon>
            <span>系统管理</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-container>
        <!-- 头部导航栏 -->
        <el-header class="header">
          <h3>{{ productName }}</h3>
          <button data-test="logout" class="logout-button" type="button" @click="logout">
            退出登录
          </button>
        </el-header>

        <!-- 页面内容 -->
        <el-main class="main-content">
          <router-view></router-view>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script>
import { HomeFilled, UploadFilled, Document } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import apiClient from '@/api/client';
import { clearToken } from '@/auth/session';
import { PRODUCT_NAME } from '@/config/branding';

export default {
  name: 'App',
  components: {
    HomeFilled,
    UploadFilled,
    Document
  },
  data() {
    return { productName: PRODUCT_NAME };
  },
  mounted() {
    window.addEventListener('auth:unauthorized', this.handleUnauthorized);
    window.addEventListener('auth:required', this.handleAuthenticationRequired);
  },
  beforeUnmount() {
    window.removeEventListener('auth:unauthorized', this.handleUnauthorized);
    window.removeEventListener('auth:required', this.handleAuthenticationRequired);
  },
  methods: {
    handleUnauthorized() {
      this.$router.replace({ name: 'Login' });
    },
    handleAuthenticationRequired() {
      ElMessage.warning('请先登录后再使用该功能');
    },
    async logout() {
      try {
        await apiClient.post('/auth/logout');
      } finally {
        clearToken();
        await this.$router.replace({ name: 'Login' });
      }
    }
  }
};
</script>

<style>
/* 全局基础样式 */
#app {
  font-family: 'Avenir', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  height: 100vh;
}

/* 布局样式 */
.el-container {
  height: 100vh;
}

/* 侧边栏样式 */
.sidebar {
  background-color: #304156;
  min-height: 100vh;
  color: #fff;
}

/* 侧边菜单样式 */
.sidebar .el-menu {
  background-color: #304156;
  border-right: none;
}

.sidebar .el-menu-item {
  color: #fff;
}

.sidebar .el-menu-item:hover {
  background-color: #263445;
}

/* 头部导航栏 */
.header {
  background-color: #409EFF;
  color: rgb(157, 0, 0);
  text-align: center;
  font-size: 20px;
  padding: 15px 0;
  position: relative;
}

.logout-button {
  position: absolute;
  top: 14px;
  right: 20px;
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 6px;
  padding: 7px 12px;
  color: #fff;
  background: transparent;
  cursor: pointer;
}

/* 主页面内容 */
.main-content {
  background: #f5f7fa;
  padding: 20px;
  min-height: calc(100vh - 60px);
}
</style>
