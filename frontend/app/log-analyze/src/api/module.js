import axios from "axios";

const VUE_APP_BASE_URL = process.env.VUE_APP_BASE_URL || 'http://localhost:5000';

const moduleApi = {

  // 获取指定产品的所有模块及其对应的分支信息
  getModulesByProduct: async (productId) => {
    try {
      const response = await axios.get(`${VUE_APP_BASE_URL}/module/get`, {
        params: { product_id: productId }
      });
      console.log(`获取产品 (ID: ${productId}) 的模块数据成功:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`获取产品 (ID: ${productId}) 的模块数据失败:`, error);
      throw error;
    }
  },

  // 创建模块
  addModule: async (moduleData) => {
    try {
      const response = await axios.post(`${VUE_APP_BASE_URL}/module/add`, moduleData);
      console.log('添加模块成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('添加模块失败:', error);
      throw error;
    }
  },

  // 编辑模块
  editModule: async (moduleData) => {
    try {
      const response = await axios.post(`${VUE_APP_BASE_URL}/module/update`, moduleData);
      console.log('编辑模块成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('编辑模块失败:', error);
      throw error;
    }
  },

  // 删除模块
  deleteModule: async (moduleId) => {
    try {
      console.log("删除传的module id:",moduleId)
      const response = await axios.post(`${VUE_APP_BASE_URL}/module/delete`, { module_id: moduleId });
      console.log(`删除模块 (ID: ${moduleId}) 成功:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`删除模块 (ID: ${moduleId}) 失败:`, error);
      throw error;
    }
  }
};

export default moduleApi;
