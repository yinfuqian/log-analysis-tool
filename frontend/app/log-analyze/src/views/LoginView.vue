<template>
  <main class="login-page">
    <form v-if="!requestMode" class="login-card" @submit.prevent="submitLogin">
      <h1>日志分析系统</h1>
      <p class="login-subtitle">请输入授权用户名和密码</p>

      <label for="login-username">用户名</label>
      <input id="login-username" v-model.trim="username" data-test="username" autocomplete="username" required />

      <label for="login-password">密码</label>
      <input id="login-password" v-model="password" data-test="password" type="password" autocomplete="current-password" required />

      <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>
      <button type="submit" :disabled="submitting">{{ submitting ? '正在登录…' : '登录' }}</button>
      <button data-test="show-account-request" class="secondary-button" type="button" @click="openRequestForm">申请账号</button>
    </form>

    <form v-else data-test="account-request-form" class="login-card" @submit.prevent="submitAccountRequest">
      <h1>申请账号</h1>
      <p class="login-subtitle">提交后由管理员处理账号申请</p>

      <label for="request-name">申请人姓名</label>
      <input id="request-name" v-model.trim="requestForm.applicant_name" data-test="request-name" required />

      <label for="request-username">申请用户名</label>
      <input id="request-username" v-model.trim="requestForm.username" data-test="request-username" autocomplete="username" required />

      <label for="request-password">申请密码</label>
      <input id="request-password" v-model="requestForm.password" data-test="request-password" type="password" autocomplete="new-password" required />

      <p v-if="requestMessage" :class="requestError ? 'login-error' : 'login-success'" role="status">{{ requestMessage }}</p>
      <button type="submit" :disabled="requestSubmitting">{{ requestSubmitting ? '正在提交…' : '提交申请' }}</button>
      <button class="secondary-button" type="button" @click="closeRequestForm">返回登录</button>
    </form>
  </main>
</template>

<script>
import apiClient from '@/api/client'
import { requestAccount } from '@/api/accountRequests'
import { setToken } from '@/auth/session'
import '@/assets/styles/login.css'

export default {
  name: 'LoginView',
  data() {
    return {
      username: '', password: '', submitting: false, errorMessage: '', requestMode: false,
      requestSubmitting: false, requestMessage: '', requestError: false,
      requestForm: { applicant_name: '', username: '', password: '' }
    }
  },
  methods: {
    async submitLogin() {
      this.submitting = true
      this.errorMessage = ''
      try {
        const response = await apiClient.post('/auth/login', { username: this.username, password: this.password })
        setToken(response.data.token)
        this.password = ''
        await this.$router.push({ name: 'LogDashboard' })
      } catch (error) {
        this.password = ''
        this.errorMessage = error?.response?.data?.message || '登录失败，请稍后重试'
      } finally {
        this.submitting = false
      }
    },
    openRequestForm() {
      this.requestMode = true
      this.requestMessage = ''
    },
    closeRequestForm() {
      this.requestForm.password = ''
      this.requestMode = false
    },
    async submitAccountRequest() {
      this.requestSubmitting = true
      this.requestMessage = ''
      this.requestError = false
      try {
        await requestAccount({ ...this.requestForm })
        this.requestMessage = '申请已提交，请等待管理员处理'
      } catch (error) {
        this.requestError = true
        this.requestMessage = error?.response?.data?.error || '账号申请失败，请联系管理员'
      } finally {
        this.requestForm.password = ''
        this.requestSubmitting = false
      }
    }
  }
}
</script>
