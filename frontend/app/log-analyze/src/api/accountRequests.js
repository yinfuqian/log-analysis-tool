/** accountRequests 模块负责前端数据访问、状态处理或页面配置。 */
import apiClient from './client'


export async function requestAccount(payload) {
  const response = await apiClient.post('/auth/account-requests', payload)
  return response.data
}
