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
