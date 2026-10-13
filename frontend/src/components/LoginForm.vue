<script setup lang="ts">
import { ref } from "vue";
import AppIcon from "./AppIcon.vue";

defineProps<{ error: string; submitting: boolean }>();
const emit = defineEmits<{ submit: [username: string, password: string] }>();
const username = ref("");
const password = ref("");

const submit = (): void =>
  emit("submit", username.value.trim(), password.value);
</script>

<template>
  <main class="login-page" data-client="web">
    <form
      class="login-card"
      aria-labelledby="login-title"
      @submit.prevent="submit"
    >
      <div class="login-brand">
        <span class="brand-mark"><AppIcon name="brand" /></span
        ><span>GEO 本地服务工作台</span>
      </div>
      <h1 id="login-title">负责人登录</h1>
      <p>进入客户 GEO 策略、内容和监测工作区</p>
      <p v-if="error" class="form-alert" role="alert">{{ error }}</p>
      <label class="field"
        ><span>用户名</span
        ><input
          v-model="username"
          name="username"
          autocomplete="username"
          required
      /></label>
      <label class="field"
        ><span>密码</span
        ><input
          v-model="password"
          name="password"
          type="password"
          autocomplete="current-password"
          required
      /></label>
      <button class="button primary full" type="submit">登录</button>
      <small>仅平台负责人可使用 · 客户第一版不登录</small>
    </form>
  </main>
</template>
