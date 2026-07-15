<template>
  <main class="login-page">
    <form class="login-card" @submit.prevent="submitLogin">
      <h1>日志分析系统</h1>
      <p class="login-subtitle">请输入授权用户名和密码</p>

      <label for="login-username">用户名</label>
      <input
        id="login-username"
        v-model.trim="username"
        data-test="username"
        autocomplete="username"
        required
      />

      <label for="login-password">密码</label>
      <input
        id="login-password"
        v-model="password"
        data-test="password"
        type="password"
        autocomplete="current-password"
        required
      />

      <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>
      <button type="submit" :disabled="submitting">
        {{ submitting ? '正在登录…' : '登录' }}
      </button>
    </form>
  </main>
</template>

<script>
import apiClient from '@/api/client'
import { setToken } from '@/auth/session'
import '@/assets/styles/login.css'

export default {
  name: 'LoginView',
  data() {
    return {
      username: '',
      password: '',
      submitting: false,
      errorMessage: ''
    }
  },
  methods: {
    async submitLogin() {
      this.submitting = true
      this.errorMessage = ''
      try {
        const response = await apiClient.post('/auth/login', {
          username: this.username,
          password: this.password
        })
        setToken(response.data.token)
        await this.$router.push({ name: 'LogDashboard' })
      } catch (error) {
        this.errorMessage = error?.response?.data?.message || '登录失败，请稍后重试'
      } finally {
        this.submitting = false
      }
    }
  }
}
</script>
