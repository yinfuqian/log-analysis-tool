import { mount } from '@vue/test-utils'

import apiClient from '@/api/client'
import App from '@/App.vue'
import { getToken, setToken } from '@/auth/session'


jest.mock('@/api/client', () => ({
  __esModule: true,
  default: { post: jest.fn() }
}))


describe('authenticated application shell', () => {
  beforeEach(() => {
    sessionStorage.clear()
    apiClient.post.mockReset()
  })

  test('logout clears the session and returns to login', async () => {
    setToken('token-value')
    apiClient.post.mockResolvedValue({ data: {} })
    const router = { replace: jest.fn() }
    const wrapper = mount(App, {
      global: {
        mocks: {
          $route: { name: 'LogDashboard', path: '/dashboard' },
          $router: router
        },
        stubs: {
          'router-view': true,
          'el-container': { template: '<div><slot /></div>' },
          'el-aside': { template: '<aside><slot /></aside>' },
          'el-menu': { template: '<nav><slot /></nav>' },
          'el-menu-item': { template: '<div><slot /></div>' },
          'el-icon': { template: '<span><slot /></span>' },
          'el-header': { template: '<header><slot /></header>' },
          'el-main': { template: '<main><slot /></main>' }
        }
      }
    })

    await wrapper.find('[data-test="logout"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(apiClient.post).toHaveBeenCalledWith('/auth/logout')
    expect(getToken()).toBeNull()
    expect(router.replace).toHaveBeenCalledWith({ name: 'Login' })
  })
})
