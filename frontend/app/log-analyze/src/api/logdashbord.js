import axios from 'axios';

const VUE_APP_BASE_URL = process.env.VUE_APP_BASE_URL || "http://localhost:5000";

const logdashbordApi = {
  async getDashboardData() {
    try {
      const response = await axios.get(`${VUE_APP_BASE_URL}/dashboard/get`);
      return response.data; 
    } catch (error) {
      console.error("API 请求失败:", error);
      throw error;  // 抛出错误以便调用者捕获
    }
  }
};

export default logdashbordApi;
