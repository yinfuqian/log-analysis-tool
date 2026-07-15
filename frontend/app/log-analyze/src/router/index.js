import { createRouter, createWebHistory } from 'vue-router';
import LogDashboard from '@/views/LogDashboard.vue';
import SystemManage from '@/views/SystemManage.vue';
import ProductManage from '@/views/ProductManage.vue';
import ModuleManage from '@/views/ModuleManage.vue';
import UploadLog from '@/components/LogUpload.vue';  // 新增的上传日志页面
import AnalysisResult from '@/components/AnalysisResult.vue';
import LoginView from '@/views/LoginView.vue';
import { authGuard } from '@/auth/guard';

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
  },
  {
    path: '/',
    redirect: '/dashboard',  // 默认跳转到日志仪表盘
  },
  {
    path: '/dashboard',
    name: 'LogDashboard',
    component: LogDashboard,
    meta: { requiresAuth: true },
  },
  {
    path: '/systemmanage',
    name: 'SystemManage',
    component: SystemManage,
    meta: { requiresAuth: true },
  },
  {
    path: '/productmanage',
    name: 'ProductManage',
    component: ProductManage,
    meta: { requiresAuth: true },
  },
  {
    path: '/modulemanage',
    name: 'ModuleManage',
    component: ModuleManage,
    meta: { requiresAuth: true },
  },
  {
    path: '/upload',
    name: 'UploadLog',
    component: UploadLog,  // 上传日志页面
    meta: { requiresAuth: true },
  },
  {
    path: '/analysis',
    name: 'AnalysisResult',
    component: AnalysisResult,
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(authGuard);

export default router;
