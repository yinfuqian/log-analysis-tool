import apiClient from './client'


export async function requestAccount(payload) {
  const response = await apiClient.post('/auth/account-requests', payload)
  return response.data
}
