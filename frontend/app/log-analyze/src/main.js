import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import { createStore } from 'vuex';
import productStore from './api/product'; // 引入 Vuex store
import axios from 'axios';

// 引入 Element Plus 及其样式
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';


console.log(process.env); 
const store = createStore({
  modules: {
    product: productStore, // 注册 product store 模块
  },
});

const app = createApp(App);
app.config.globalProperties.$axios = axios;

// 使用 Vue Router, Element Plus 和 Vuex


app.use(router);
app.use(store);
app.use(ElementPlus);

// 挂载应用
app.mount('#app');
