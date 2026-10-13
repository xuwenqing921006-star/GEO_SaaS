<script setup lang="ts">
/* eslint-disable vue/multiline-html-element-content-newline */
import { useQuery } from "@tanstack/vue-query";
import { Button as AButton } from "ant-design-vue";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getClient } from "../api/clients";
import { useWorkspaceStore } from "../stores/workspace";
import AppIcon from "./AppIcon.vue";
const workspace = useWorkspaceStore();
const route = useRoute();
const router = useRouter();
const isDevelopmentMock =
  import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "true";
const routeClientId = computed(() =>
  typeof route.query.clientId === "string" ? route.query.clientId : "",
);
const clientQuery = useQuery({
  queryKey: computed(() => ["client", routeClientId.value]),
  queryFn: () => getClient(routeClientId.value),
  enabled: computed(() => Boolean(routeClientId.value)),
});
const contextClient = computed(() =>
  routeClientId.value
    ? (clientQuery.data.value ?? null)
    : workspace.currentClient,
);
const clientStatusLabel = computed(() => {
  const status = contextClient.value?.status;
  if (status === "active") return "服务中";
  if (status === "paused") return "已暂停";
  if (status === "archived") return "已归档";
  return "—";
});
const modules = [
  {
    icon: "knowledge",
    label: "企业知识库",
    routeName: "knowledge",
    available: true,
  },
  {
    icon: "diagnostics",
    label: "GEO 诊断",
    routeName: "diagnostics",
    available: true,
  },
  {
    icon: "strategy",
    label: "关键词",
    routeName: "strategy",
    available: true,
  },
  {
    icon: "content",
    label: "内容工作台",
    routeName: "content",
    available: true,
  },
  {
    icon: "publishing",
    label: "文章发布",
    routeName: "publishing",
    available: true,
  },
  {
    icon: "channels",
    label: "渠道配置",
    routeName: "channels",
    available: true,
  },
  {
    icon: "settings",
    label: "系统设置",
    routeName: "settings",
    available: true,
  },
] as const;
const emit = defineEmits<{ search: []; account: [] }>();
const navigate = (
  routeName:
    | "knowledge"
    | "diagnostics"
    | "strategy"
    | "content"
    | "publishing"
    | "channels"
    | "settings",
): void => {
  const clientId = routeClientId.value
    ? routeClientId.value
    : workspace.currentClientId;
  void router.push({ name: routeName, query: clientId ? { clientId } : {} });
};
</script>
<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
        <span class="brand-mark"><AppIcon name="brand" /></span
        ><span>GEO SaaS</span>
      </div>
      <nav>
        <button
          class="nav-item"
          :class="{ active: route.name === 'clients' }"
          type="button"
          aria-label="客户工作台"
          @click="router.push({ name: 'clients', query: route.query })"
        >
          <span class="nav-icon" aria-hidden="true"
            ><AppIcon name="clients" /></span
          ><span class="nav-label">客户工作台</span></button
        ><button
          v-for="item in modules"
          :key="item.routeName"
          class="nav-item"
          :class="{
            active: route.name === item.routeName,
            unavailable: !item.available,
          }"
          type="button"
          :disabled="!item.available"
          :aria-label="item.label"
          :title="item.available ? item.label : `${item.label}为后续模块`"
          @click="
            item.available &&
            navigate(
              item.routeName as
                | 'knowledge'
                | 'diagnostics'
                | 'strategy'
                | 'content'
                | 'publishing'
                | 'channels'
                | 'settings',
            )
          "
        >
          <span class="nav-icon" aria-hidden="true"
            ><AppIcon :name="item.icon" /></span
          ><span class="nav-label">{{ item.label }}</span
          ><small v-if="!item.available">后续模块</small>
        </button>
      </nav>
    </aside>
    <section class="shell-content">
      <header class="topbar">
        <div class="client-context">
          <strong>{{ contextClient?.standard_name ?? "正在载入客户" }}</strong
          ><span>{{
            contextClient
              ? `${contextClient.city} · ${contextClient.industry_name}`
              : routeClientId
                ? "客户资料暂时无法载入"
                : "选择客户查看工作台"
          }}</span>
        </div>
        <section
          v-if="contextClient"
          class="result-track"
          :aria-label="`${contextClient.standard_name}的工作台摘要${isDevelopmentMock ? '（开发预览）' : ''}`"
        >
          <div>
            <span>资料完整度</span>
            <strong>{{ contextClient.fact_completeness }}%</strong>
          </div>
          <div>
            <span>服务地区</span>
            <strong>{{ contextClient.district || contextClient.city }}</strong>
          </div>
          <div>
            <span>客户状态</span>
            <strong>{{ clientStatusLabel }}</strong>
          </div>
          <div class="track-next">
            <span>下一步 <small v-if="isDevelopmentMock">开发预览</small></span>
            <strong>待处理：{{ contextClient.next_action }}</strong>
          </div>
        </section>
        <AButton
          v-if="route.name === 'clients'"
          class="search-shortcut"
          aria-label="聚焦搜索客户"
          @click="emit('search')"
        >
          搜索客户 <kbd>/</kbd> </AButton
        ><button
          class="link-button"
          type="button"
          aria-label="账户菜单"
          @click="emit('account')"
        >
          账户菜单
        </button>
      </header>
      <slot />
    </section>
  </div>
</template>
