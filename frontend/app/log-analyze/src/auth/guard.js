import { getToken } from './session'


export function authGuard(to) {
  if (to.name === 'Login' && getToken()) {
    return { name: 'LogDashboard' }
  }
  return true
}
