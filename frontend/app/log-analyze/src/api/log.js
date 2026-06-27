import axios from "axios";

const VUE_APP_BASE_URL = process.env.VUE_APP_BASE_URL || "http://localhost:5000";

const LogApi = {

  // 上传日志文件
  uploadLog(file, params) {
    const formData = new FormData();
    formData.append("file", file);
    Object.keys(params).forEach((key) => {
      formData.append(key, params[key]);
    });

    return axios.post(`${VUE_APP_BASE_URL}/api/upload`, formData, {
    });
  },
};

export default LogApi;
