<script setup lang="ts">
import { computed, ref } from "vue";
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
type PublishingState = {
  selectedCount: number;
  isPublishing: boolean;
  visible: boolean;
};
type PublishingWorkbenchExpose = {
  publishSelectedDocuments: () => Promise<void>;
};
const workbench = ref<PublishingWorkbenchExpose | null>(null);
const publishingState = ref<PublishingState>({
  selectedCount: 0,
  isPublishing: false,
  visible: false,
});
const updatePublishingState = (state: PublishingState): void => {
  publishingState.value = state;
};
const publishSelectedDocuments = async (): Promise<void> => {
  await workbench.value?.publishSelectedDocuments();
};
</script>

<template>
  <AppShell>
    <main class="workspace content-page publishing-page">
      <header class="page-head publishing-page-head">
        <div>
          <p class="eyebrow">CONTENT DISTRIBUTION · 文章发布</p>
          <h1>文章发布</h1>
          <p>
            这里只展示已在内容工作台确认、并通过质量检查的文章，可单篇或批量提交到指定平台。
          </p>
        </div>
        <div class="publishing-page-actions" aria-label="文章发布操作">
          <button
            v-if="publishingState.visible"
            class="button primary publishing-page-batch-action"
            type="button"
            :disabled="
              publishingState.selectedCount === 0 ||
              publishingState.isPublishing
            "
            @click="publishSelectedDocuments"
          >
            {{
              publishingState.isPublishing
                ? "批量发布中…"
                : `批量发布 (${publishingState.selectedCount})`
            }}
          </button>
        </div>
      </header>
      <section v-if="!clientId" class="panel empty-panel">
        <h2>请先选择客户</h2>
        <p>文章和发布记录必须绑定当前客户，避免跨客户误操作。</p>
      </section>
      <ContentWorkbench
        v-else
        ref="workbench"
        :key="clientId"
        :client-id="clientId"
        :client-name="clientName"
        mode="publishing"
        @publishing-state="updatePublishingState"
      />
    </main>
  </AppShell>
</template>
