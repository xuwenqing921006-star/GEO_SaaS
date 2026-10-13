<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";
import { useWorkspaceStore } from "../stores/workspace";
import ContentWorkbench from "./ContentWorkbench.vue";

const route = useRoute();
const workspace = useWorkspaceStore();
const clientId = computed(() =>
  typeof route.query.clientId === "string"
    ? route.query.clientId
    : workspace.currentClientId,
);
const clientName = computed(
  () => workspace.currentClient?.standard_name ?? "当前客户",
);
</script>

<template>
  <AppShell>
    <main class="workspace content-page">
      <header class="page-head">
        <div>
          <p class="eyebrow">AI CONTENT · 内容工作台</p>
          <h1>内容工作台</h1>
          <p>
            AI 根据已选关键词、企业知识库和 GEO
            建议批量生成文章；生成进度和本次文章可在任务列表查看，完整文章统一进入“文章发布”。
          </p>
        </div>
      </header>
      <section v-if="!clientId" class="panel empty-panel">
        <h2>请先选择客户</h2>
        <p>文章必须绑定当前客户的关键词和企业资料，避免信息混用。</p>
      </section>
      <ContentWorkbench
        v-else
        :key="clientId"
        :client-id="clientId"
        :client-name="clientName"
      />
    </main>
  </AppShell>
</template>
