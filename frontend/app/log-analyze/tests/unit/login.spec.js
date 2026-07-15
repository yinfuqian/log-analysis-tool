import { mount } from '@vue/test-utils'

import apiClient from '@/api/client'
import { getToken } from '@/auth/session'
import LoginView from '@/views/LoginView.vue'


jest.mock('@/api/client', () => ({
  __esModule: true,
  default: { post: jest.fn() }
}))


describe('LoginView', () => {
  beforeEach(() => {
    sessionStorage.clear()
    apiClient.post.mockReset()
  })

  test('logs in and enters the dashboard', async () => {
    apiClient.post.mockResolvedValue({ data: { token: 'server-token', username: 'alice' } })
    const router = { push: jest.fn() }
    const wrapper = mount(LoginView, { global: { mocks: { $router: router } } })

    await wrapper.find('[data-test="username"]').setValue('alice')
    await wrapper.find('[data-test="password"]').setValue('secret')
    await wrapper.find('form').trigger('submit.prevent')
    await wrapper.vm.$nextTick()

    expect(apiClient.post).toHaveBeenCalledWith('/auth/login', { username: 'alice', password: 'secret' })
    expect(getToken()).toBe('server-token')
    expect(router.push).toHaveBeenCalledWith({ name: 'LogDashboard' })
  })

  test('shows the safe backend error message', async () => {
    apiClient.post.mockRejectedValue({ response: { data: { message: '用户名或密码错误' } } })
    const wrapper = mount(LoginView, { global: { mocks: { $router: { push: jest.fn() } } } })

    await wrapper.find('[data-test="username"]').setValue('alice')
    await wrapper.find('[data-test="password"]').setValue('wrong')
    await wrapper.find('form').trigger('submit.prevent')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('用户名或密码错误')
  })
})
