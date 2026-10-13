<script setup lang="ts">
import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { login } from "../api/auth";
import LoginForm from "../components/LoginForm.vue";
import { useSessionStore } from "../stores/session";
const router = useRouter();
const route = useRoute();
const session = useSessionStore();
const error = ref("");
const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: ({
    username,
    password,
  }: {
    username: string;
    password: string;
  }) => login(username, password),
  onSuccess: async (data) => {
    session.setSession(data);
    queryClient.clear();
    await router.replace(
      typeof route.query.redirect === "string"
        ? route.query.redirect
        : "/clients",
    );
  },
  onError: () => {
    error.value = "用户名或密码错误";
  },
});
const submitting = computed(() => mutation.isPending.value);
</script>
<template>
  <LoginForm
    :error="error"
    :submitting="submitting"
    @submit="(username, password) => mutation.mutate({ username, password })"
  />
</template>
