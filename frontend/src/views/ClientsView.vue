<script setup lang="ts">
/* eslint-disable vue/multiline-html-element-content-newline */
import { nextTick, onMounted, onUnmounted, ref } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import { changePassword, logout } from "../api/auth";
import AppShell from "../components/AppShell.vue";
import ClientWorkspace from "../components/ClientWorkspace.vue";
import ModalDialog from "../components/ModalDialog.vue";
import { useSessionStore } from "../stores/session";
import { useWorkspaceStore } from "../stores/workspace";
const router = useRouter();
const session = useSessionStore();
const workspace = useWorkspaceStore();
const queryClient = useQueryClient();
const accountOpen = ref(false);
const passwordOpen = ref(false);
const currentPassword = ref("");
const newPassword = ref("");
const accountError = ref("");
const accountErrorAction = ref<"logout" | "password" | null>(null);
const workspaceRef = ref<{ requestLogout: () => void } | null>(null);
const focusSearch = (): void => {
  document.querySelector<HTMLInputElement>("[role=searchbox]")?.focus();
};
const clearAccountError = (): void => {
  accountError.value = "";
  accountErrorAction.value = null;
};
const openAccount = (): void => {
  if (accountErrorAction.value === "password") clearAccountError();
  accountOpen.value = true;
};
const closeAccount = (): void => {
  accountOpen.value = false;
  if (accountErrorAction.value === "logout") clearAccountError();
};
const openPassword = (): void => {
  clearAccountError();
  passwordOpen.value = true;
  accountOpen.value = false;
};
const closePassword = (): void => {
  passwordOpen.value = false;
  if (accountErrorAction.value === "password") clearAccountError();
};
const signOut = async (): Promise<void> => {
  clearAccountError();
  try {
    await logout();
    session.clearSession();
    workspace.clear();
    queryClient.clear();
    await router.replace("/login");
  } catch {
    accountError.value = "退出失败，请重试";
    accountErrorAction.value = "logout";
    passwordOpen.value = false;
    accountOpen.value = true;
    await nextTick();
  }
};
const requestSignOut = async (): Promise<void> => {
  if (workspace.isDirty) {
    accountOpen.value = false;
    passwordOpen.value = false;
    await nextTick();
  }
  workspaceRef.value?.requestLogout();
};
const savePassword = async (): Promise<void> => {
  clearAccountError();
  try {
    const result = await changePassword(
      currentPassword.value,
      newPassword.value,
    );
    currentPassword.value = "";
    newPassword.value = "";
    if (result.relogin_required) {
      session.clearSession();
      workspace.clear();
      queryClient.clear();
      passwordOpen.value = false;
      accountOpen.value = false;
      await router.replace("/login");
      return;
    }
    passwordOpen.value = false;
    accountOpen.value = true;
  } catch {
    accountError.value = "修改密码失败，请重试";
    accountErrorAction.value = "password";
    passwordOpen.value = true;
    accountOpen.value = false;
  }
};
const onUnauthorized = async (): Promise<void> => {
  const redirect = router.currentRoute.value.fullPath;
  session.clearSession();
  workspace.clear();
  queryClient.clear();
  await router.replace({ name: "login", query: { redirect } });
};
onMounted(() => window.addEventListener("geo:unauthorized", onUnauthorized));
onUnmounted(() =>
  window.removeEventListener("geo:unauthorized", onUnauthorized),
);
</script>
<template>
  <AppShell @search="focusSearch" @account="openAccount">
    <ClientWorkspace ref="workspaceRef" @logout="signOut" /> </AppShell
  ><ModalDialog
    v-if="accountOpen"
    title="账户菜单"
    size="small"
    @close="closeAccount"
  >
    <p
      v-if="accountError && accountErrorAction === 'logout'"
      class="state-error"
      role="alert"
    >
      {{ accountError }} <button class="button" @click="signOut">重试</button>
    </p>
    <footer class="modal-actions">
      <button class="button" @click="openPassword">修改密码</button
      ><button class="button danger" @click="requestSignOut">退出登录</button>
    </footer> </ModalDialog
  ><ModalDialog
    v-if="passwordOpen"
    title="修改密码"
    size="small"
    @close="closePassword"
  >
    <label class="field"
      ><span>当前密码</span
      ><input v-model="currentPassword" type="password" /></label
    ><label class="field"
      ><span>新密码</span><input v-model="newPassword" type="password"
    /></label>
    <footer class="modal-actions">
      <button class="button primary" @click="savePassword">确认修改密码</button>
      <button class="button danger" @click="requestSignOut">退出登录</button>
    </footer>
    <p
      v-if="accountError && accountErrorAction === 'password'"
      class="state-error"
      role="alert"
    >
      {{ accountError }}
      <button class="button" @click="savePassword">重试</button>
    </p>
  </ModalDialog>
</template>
