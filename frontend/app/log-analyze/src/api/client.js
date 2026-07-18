/** client 模块负责前端数据访问、状态处理或页面配置。 */
import axios from 'axios'

import { clearToken, getToken } from '@/auth/session'


const baseURL = process.env.VUE_APP_BASE_URL || 'http://localhost:5000'


export function applyAuthHeader(config) {
  const token = getToken()
  if (!token) {
    return config
  }
  config.headers = config.headers || {}
  if (typeof config.headers.set === 'function') {
    config.headers.set('Authorization', `Bearer ${token}`)
  } else {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}


export function handleUnauthorized() {
  const hadToken = Boolean(getToken())
  clearToken()
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(hadToken ? 'auth:unauthorized' : 'auth:required'))
  }
}


const apiClient = axios.create({ baseURL, timeout: 30000 })
apiClient.interceptors.request.use(applyAuthHeader)
apiClient.interceptors.response.use(
  response => response,
  error => {
    if (error?.response?.status === 401) {
      handleUnauthorized()
    }
    return Promise.reject(error)
  }
)

export default apiClient
