/** logdashbord 模块负责前端数据访问、状态处理或页面配置。 */
import apiClient from './client';

const logdashbordApi = {
  async getDashboardData() {
    try {
      const response = await apiClient.get('/dashboard/get');
      return response.data; 
    } catch (error) {
      console.error("API 请求失败:", error);
      throw error;  // 抛出错误以便调用者捕获
    }
  }
};

export default logdashbordApi;
