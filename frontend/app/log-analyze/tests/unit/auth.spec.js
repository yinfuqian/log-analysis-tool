jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => ({
      interceptors: {
        request: { use: jest.fn() },
        response: { use: jest.fn() }
      }
    }))
  }
}))

import { clearToken, getToken, setToken } from '@/auth/session'
import { applyAuthHeader, handleUnauthorized } from '@/api/client'
import { authGuard } from '@/auth/guard'


describe('application session', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  test('stores the token only in session storage', () => {
    setToken('token-value')

    expect(getToken()).toBe('token-value')
    expect(localStorage.getItem('log-analyzer-session')).toBeNull()
  })

  test('clears the current token', () => {
    setToken('token-value')

    clearToken()

    expect(getToken()).toBeNull()
  })

  test('adds the bearer token to API requests', () => {
    setToken('token-value')

    const config = applyAuthHeader({ headers: {} })

    expect(config.headers.Authorization).toBe('Bearer token-value')
  })

  test('401 handling clears an expired session', () => {
    setToken('token-value')

    handleUnauthorized()

    expect(getToken()).toBeNull()
  })

  test('anonymous 401 asks for login without treating it as an expired session', () => {
    const required = jest.fn()
    window.addEventListener('auth:required', required, { once: true })

    handleUnauthorized()

    expect(required).toHaveBeenCalledTimes(1)
  })

  test('anonymous users can browse business routes', () => {
    const result = authGuard({ name: 'Dashboard', meta: { requiresAuth: true } })

    expect(result).toBe(true)
  })

  test('authenticated users can enter protected routes', () => {
    setToken('token-value')

    expect(authGuard({ name: 'Dashboard', meta: { requiresAuth: true } })).toBe(true)
  })
})
