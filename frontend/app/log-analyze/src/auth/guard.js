/** guard 模块负责前端数据访问、状态处理或页面配置。 */
import { getToken } from './session'


export function authGuard(to) {
  if (to.name === 'Login' && getToken()) {
    return { name: 'LogDashboard' }
  }
  return true
}
