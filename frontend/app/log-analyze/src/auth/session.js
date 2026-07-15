const SESSION_KEY = 'log-analyzer-session'


export function getToken() {
  return window.sessionStorage.getItem(SESSION_KEY)
}


export function setToken(token) {
  window.sessionStorage.setItem(SESSION_KEY, token)
}


export function clearToken() {
  window.sessionStorage.removeItem(SESSION_KEY)
}
