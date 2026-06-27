import ProductManage from '@/views/ProductManage.vue';
import ModuleManage from '@/views/ModuleManage.vue';

export default {
  components: { ProductManage, ModuleManage },
  props: ['tab'],
  data() {
    return {
      activeTab: this.tab || 'product',  // 默认激活的 tab 为 'product'
    };
  },
  watch: {
    activeTab(newTab) {
      // 更新路由时，tab 参数会变成新的值
      this.$router.push({ path: '/modulemanage', query: { tab: newTab } });
    },
  },
  created() {
    // 从 URL 查询中获取 tab 参数来设置默认的 activeTab
    if (this.$route.query.tab) {
      this.activeTab = this.$route.query.tab;
    }
  },
};