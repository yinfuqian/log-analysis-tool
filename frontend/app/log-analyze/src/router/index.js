import { createRouter, createWebHistory } from 'vue-router';
import LogDashboard from '@/views/LogDashboard.vue';
import SystemManage from '@/views/SystemManage.vue';
import ProductManage from '@/views/ProductManage.vue';
import ModuleManage from '@/views/ModuleManage.vue';
import UploadLog from '@/components/LogUpload.vue';  // 新增的上传日志页面
import AnalysisResult from '@/components/AnalysisResult.vue';

const routes = [
  {
    path: '/',
    redirect: '/dashboard',  // 默认跳转到日志仪表盘
  },
  {
    path: '/dashboard',
    name: 'LogDashboard',
    component: LogDashboard,
  },
  {
    path: '/systemmanage',
    name: 'SystemManage',
    component: SystemManage,
  },
  {
    path: '/productmanage',
    name: 'ProductManage',
    component: ProductManage,
  },
  {
    path: '/modulemanage',
    name: 'ModuleManage',
    component: ModuleManage,
  },
  {
    path: '/upload',
    name: 'UploadLog',
    component: UploadLog,  // 上传日志页面
  },
  {
    path: '/analysis',
    name: 'AnalysisResult',
    component: AnalysisResult,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
