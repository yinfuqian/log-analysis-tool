import { getToken } from './session'


export function authGuard(to) {
  if (to.meta?.requiresAuth && !getToken()) {
    return { name: 'Login' }
  }
  if (to.name === 'Login' && getToken()) {
    return { name: 'LogDashboard' }
  }
  return true
}
