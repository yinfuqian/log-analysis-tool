import axios from "axios";

const VUE_APP_BASE_URL = process.env.VUE_APP_BASE_URL || 'http://localhost:5000';

const productApi = {

  // 获取产品数据
  getProducts: async () => {
    try {
      const response = await axios.get(`${VUE_APP_BASE_URL}/product/get`);
      console.log('获取产品数据成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('获取产品数据失败:', error);
      throw error;
    }
  },

  // 编辑产品接口，使用 POST 方法
  editProduct: async (productData) => {
    try {
      // 向后端发送 POST 请求，传递更新的数据
      const response = await axios.post(`${VUE_APP_BASE_URL}/product/edit`, productData);
      console.log('编辑产品成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('编辑产品失败:', error);
      throw error;
    }
  },

  // 删除产品
  deleteProduct: async (productId) => {
    try {
      const response = await axios.post(`${VUE_APP_BASE_URL}/product/delete`, { id: productId });
      console.log('删除产品成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('删除产品失败:', error);
      throw error;
    }
  },
  
  //创建产品
  addProduct: async (productData) => {
    try {
      const response = await axios.post(`${VUE_APP_BASE_URL}/product/add`, productData);
      console.log(productData)
      console.log('添加产品成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('添加产品失败:', error);
      throw error;
    }
  }

};
export default productApi;
