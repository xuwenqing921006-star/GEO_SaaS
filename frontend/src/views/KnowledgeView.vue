<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import {
  createFact,
  deleteMaterial,
  extractMaterial,
  listFacts,
  listMaterials,
  materialFileUrl,
  updateFact,
  uploadMaterials,
} from "../api/knowledge";
import type { FactData, MaterialData } from "../api/dto";
import AppShell from "../components/AppShell.vue";
import ModalDialog from "../components/ModalDialog.vue";
import {
  notifyRequestError,
  notifyRequestInfo,
  notifyRequestSuccess,
} from "../requestNotifications";
import { useWorkspaceStore } from "../stores/workspace";

interface KnowledgeCategory {
  value: FactData["category"];
  label: string;
  description: string;
  primaryKey: string;
}

const categories: KnowledgeCategory[] = [
  {
    value: "identity",
    label: "企业信息",
    description: "企业名称、品牌介绍和基本信息",
    primaryKey: "identity.standard_name",
  },
  {
    value: "location",
    label: "地区范围",
    description: "所在地区、门店地址和服务范围",
    primaryKey: "location.service_area",
  },
  {
    value: "service",
    label: "服务产品",
    description: "主营服务、产品和课程项目",
    primaryKey: "service.primary",
  },
  {
    value: "audience",
    label: "服务对象",
    description: "适合的客户、人群和使用场景",
    primaryKey: "audience.primary",
  },
  {
    value: "price",
    label: "价格信息",
    description: "收费方式、价格区间和价格说明",
    primaryKey: "price.primary",
  },
  {
    value: "process",
    label: "服务流程",
    description: "咨询、预约、交付和售后流程",
    primaryKey: "process.primary",
  },
  {
    value: "capability",
    label: "企业优势",
    description: "团队、资质、经验和服务能力",
    primaryKey: "capability.primary",
  },
  {
    value: "case",
    label: "案例成果",
    description: "真实案例、项目成果和客户反馈",
    primaryKey: "case.primary",
  },
  {
    value: "contact",
    label: "联系信息",
    description: "电话、微信、营业时间等公开信息",
    primaryKey: "contact.public",
  },
  {
    value: "restriction",
    label: "补充说明",
    description: "其他需要让 AI 了解的企业信息",
    primaryKey: "restriction.primary",
  },
];

const route = useRoute();
const workspace = useWorkspaceStore();
const accountOpen = ref(false);
const searchText = ref("");
const categoryFilter = ref<FactData["category"] | "all">("all");
const selectedFiles = ref<File[]>([]);
const selectedImageFiles = ref<File[]>([]);
const uploadState = ref<"idle" | "queued" | "running" | "succeeded" | "failed">(
  "idle",
);
const uploadError = ref("");
const imageUploadState = ref<
  "idle" | "queued" | "running" | "succeeded" | "failed"
>("idle");
const imageUploadError = ref("");
const pendingDeleteImage = ref<MaterialData | null>(null);
const imageDeleting = ref(false);
const imageDeleteError = ref("");
const editorOpen = ref(false);
const editingFact = ref<FactData | null>(null);
const draftCategory = ref<FactData["category"]>("service");
const draftLabel = ref("");
const draftValue = ref("");
const factSaving = ref(false);
const factError = ref("");
const pendingImportMaterialIds = ref<string[]>([]);

const clientId = computed(() =>
  typeof route.query.clientId === "string"
    ? route.query.clientId
    : workspace.currentClientId,
);
const enabled = computed(() => Boolean(clientId.value));

const materialsQuery = useQuery({
  queryKey: computed(() => ["materials", clientId.value]),
  queryFn: () => listMaterials(clientId.value),
  enabled,
  refetchInterval: (query) =>
    query.state.data?.items.some((item) =>
      ["queued", "running"].includes(item.extraction_status),
    )
      ? 5000
      : false,
});
const factsQuery = useQuery({
  queryKey: computed(() => ["facts", clientId.value]),
  queryFn: () => listFacts(clientId.value),
  enabled,
});

const isLoading = computed(
  () => materialsQuery.isPending.value || factsQuery.isPending.value,
);
const hasLoadError = computed(
  () => materialsQuery.isError.value || factsQuery.isError.value,
);
const knowledgeItems = computed(
  () =>
    factsQuery.data.value?.items.filter(
      (item) => !["private", "conflict"].includes(item.status),
    ) ?? [],
);
const imageMaterials = computed(
  () =>
    materialsQuery.data.value?.items.filter(
      (item) => item.category === "image",
    ) ?? [],
);
const documentMaterials = computed(
  () =>
    materialsQuery.data.value?.items.filter(
      (item) => item.category !== "image",
    ) ?? [],
);
const filteredItems = computed(() => {
  const keyword = searchText.value.trim().toLocaleLowerCase("zh-CN");
  return knowledgeItems.value.filter((item) => {
    const matchesCategory =
      categoryFilter.value === "all" || item.category === categoryFilter.value;
    const matchesKeyword =
      !keyword ||
      item.label.toLocaleLowerCase("zh-CN").includes(keyword) ||
      item.value.toLocaleLowerCase("zh-CN").includes(keyword);
    return matchesCategory && matchesKeyword;
  });
});
const representedCategories = computed(
  () => new Set(knowledgeItems.value.map((item) => item.category)).size,
);
const categoryCounts = computed(() =>
  categories
    .map((category) => ({
      ...category,
      count: knowledgeItems.value.filter(
        (item) => item.category === category.value,
      ).length,
    }))
    .filter((category) => category.count > 0),
);
const latestUpdated = computed(() => {
  const dates = [
    ...knowledgeItems.value.map((item) => item.updated_at),
    ...(materialsQuery.data.value?.items.map((item) => item.uploaded_at) ?? []),
  ]
    .map((item) => new Date(item).getTime())
    .filter((item) => Number.isFinite(item));
  return dates.length ? new Date(Math.max(...dates)) : null;
});

watch(
  () =>
    materialsQuery.data.value?.items
      .filter((item) => item.category !== "image")
      .map((item) => `${item.id}:${item.extraction_status}`)
      .join("|"),
  (current, previous) => {
    if (
      previous &&
      current !== previous &&
      materialsQuery.data.value?.items.some(
        (item) => item.extraction_status === "succeeded",
      )
    ) {
      void factsQuery.refetch();
    }
    if (!pendingImportMaterialIds.value.length) return;
    const pendingIds = new Set(pendingImportMaterialIds.value);
    const materials = (materialsQuery.data.value?.items ?? []).filter((item) =>
      pendingIds.has(item.id),
    );
    if (materials.length !== pendingIds.size) return;
    if (
      materials.some((item) =>
        ["not_started", "queued", "running"].includes(item.extraction_status),
      )
    )
      return;
    const failed = materials.filter(
      (item) => item.extraction_status === "failed",
    ).length;
    if (failed) {
      notifyRequestError(
        "知识库资料整理未全部完成",
        `成功 ${materials.length - failed} 份，失败 ${failed} 份`,
      );
    } else {
      notifyRequestSuccess(
        "知识库资料整理完成",
        `${materials.length} 份资料已生成知识条目`,
      );
    }
    pendingImportMaterialIds.value = [];
  },
);

watch(
  () => [
    uploadError.value,
    imageUploadError.value,
    imageDeleteError.value,
    factError.value,
  ],
  (errors) => {
    const message = errors.find(Boolean);
    if (message) notifyRequestError("知识库操作未完成", message);
  },
);

watch(clientId, () => {
  selectedFiles.value = [];
  selectedImageFiles.value = [];
  uploadState.value = "idle";
  imageUploadState.value = "idle";
  uploadError.value = "";
  imageUploadError.value = "";
  pendingDeleteImage.value = null;
  imageDeleteError.value = "";
  editorOpen.value = false;
  editingFact.value = null;
  searchText.value = "";
  categoryFilter.value = "all";
  pendingImportMaterialIds.value = [];
});

const retryLoad = (): void => {
  void Promise.all([materialsQuery.refetch(), factsQuery.refetch()]);
};

const chooseFiles = (event: Event): void => {
  const input = event.target as HTMLInputElement;
  selectedFiles.value = [...(input.files ?? [])];
  uploadState.value = selectedFiles.value.length ? "queued" : "idle";
};

const chooseImageFiles = (event: Event): void => {
  const input = event.target as HTMLInputElement;
  selectedImageFiles.value = [...(input.files ?? [])];
  imageUploadState.value = selectedImageFiles.value.length ? "queued" : "idle";
};

const startUpload = async (): Promise<void> => {
  if (!clientId.value || !selectedFiles.value.length) return;
  uploadState.value = "running";
  uploadError.value = "";
  try {
    const uploaded = await uploadMaterials(
      clientId.value,
      selectedFiles.value,
      "other",
      "authorized",
    );
    await Promise.all(
      uploaded.items.map((material) =>
        extractMaterial(material.id, crypto.randomUUID()),
      ),
    );
    pendingImportMaterialIds.value = uploaded.items.map((item) => item.id);
    selectedFiles.value = [];
    uploadState.value = "succeeded";
    notifyRequestInfo(
      "资料上传完成，正在整理",
      "系统会自动更新知识条目并通知最终结果，无需手动刷新",
    );
    await materialsQuery.refetch();
  } catch (error) {
    uploadState.value = "failed";
    uploadError.value =
      error instanceof Error ? error.message : "资料上传失败，请稍后重试";
  }
};

const startImageUpload = async (): Promise<void> => {
  if (!clientId.value || !selectedImageFiles.value.length) return;
  imageUploadState.value = "running";
  imageUploadError.value = "";
  try {
    await uploadMaterials(
      clientId.value,
      selectedImageFiles.value,
      "image",
      "authorized",
    );
    selectedImageFiles.value = [];
    imageUploadState.value = "succeeded";
    notifyRequestSuccess("企业图片上传完成", "图片已加入企业图片库");
    await materialsQuery.refetch();
  } catch (error) {
    imageUploadState.value = "failed";
    imageUploadError.value =
      error instanceof Error ? error.message : "企业图片上传失败，请稍后重试";
  }
};

const confirmDeleteImage = async (): Promise<void> => {
  if (!pendingDeleteImage.value) return;
  imageDeleting.value = true;
  imageDeleteError.value = "";
  try {
    await deleteMaterial(pendingDeleteImage.value.id);
    pendingDeleteImage.value = null;
    notifyRequestSuccess("企业图片已删除");
    await materialsQuery.refetch();
  } catch (error) {
    imageDeleteError.value =
      error instanceof Error ? error.message : "图片删除失败，请稍后重试";
  } finally {
    imageDeleting.value = false;
  }
};

const openCreateEditor = (): void => {
  editingFact.value = null;
  draftCategory.value = "service";
  draftLabel.value = "";
  draftValue.value = "";
  factError.value = "";
  editorOpen.value = true;
};

const openEditEditor = (fact: FactData): void => {
  editingFact.value = fact;
  draftCategory.value = fact.category;
  draftLabel.value = fact.label;
  draftValue.value = fact.value;
  factError.value = "";
  editorOpen.value = true;
};

const nextFactKey = (): string => {
  const category = categories.find(
    (item) => item.value === draftCategory.value,
  )!;
  const primaryExists = factsQuery.data.value?.items.some(
    (item) => item.key === category.primaryKey,
  );
  return primaryExists
    ? `${category.value}.entry.${crypto.randomUUID()}`
    : category.primaryKey;
};

const saveKnowledgeItem = async (): Promise<void> => {
  if (!clientId.value || !draftLabel.value.trim() || !draftValue.value.trim())
    return;
  factSaving.value = true;
  factError.value = "";
  try {
    if (editingFact.value) {
      await updateFact(editingFact.value.id, editingFact.value.version, {
        label: draftLabel.value.trim(),
        value: draftValue.value.trim(),
      });
    } else {
      await createFact(clientId.value, {
        category: draftCategory.value,
        key: nextFactKey(),
        label: draftLabel.value.trim(),
        value: draftValue.value.trim(),
        status: "client_provided",
      });
    }
    editorOpen.value = false;
    editingFact.value = null;
    notifyRequestSuccess("知识条目已保存", "后续诊断与内容生成将使用最新资料");
    await factsQuery.refetch();
  } catch (error) {
    factError.value =
      error instanceof Error ? error.message : "知识条目保存失败";
  } finally {
    factSaving.value = false;
  }
};

const categoryLabel = (category: FactData["category"]): string =>
  categories.find((item) => item.value === category)?.label ?? "其他信息";

const materialStatus = (status: MaterialData["extraction_status"]): string =>
  ({
    not_started: "待处理",
    queued: "等待整理",
    running: "正在整理",
    succeeded: "已导入",
    failed: "导入失败",
  })[status];

const formatDate = (value: string | Date): string =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
</script>

<template>
  <AppShell @account="accountOpen = true">
    <main class="workspace knowledge-manager-page">
      <header class="page-head knowledge-manager-head">
        <div>
          <p class="eyebrow">企业资料中心</p>
          <h1>企业知识库</h1>
          <p>
            集中管理 AI 需要了解的企业信息，录入或更新后直接用于 GEO
            分析和内容生成。
          </p>
        </div>
      </header>

      <section v-if="!clientId" class="panel empty-panel">
        <h2>先选择一个客户</h2>
        <p>每个客户拥有独立的企业知识库，选择客户后即可录入和管理资料。</p>
        <RouterLink class="button primary" :to="{ name: 'clients' }">
          前往客户工作台
        </RouterLink>
      </section>

      <section v-else-if="hasLoadError" class="panel error-panel" role="alert">
        <h2>企业知识库暂时无法载入</h2>
        <p>请确认服务状态后重新载入，已有资料不会丢失。</p>
        <button class="button primary" type="button" @click="retryLoad">
          重新载入
        </button>
      </section>

      <section
        v-else-if="isLoading"
        class="panel loading-panel"
        aria-busy="true"
      >
        <h2>正在载入企业知识库</h2>
        <p>正在读取企业资料和知识条目…</p>
      </section>

      <template v-else>
        <section class="knowledge-manager-summary" aria-label="知识库概览">
          <article class="knowledge-summary-card">
            <span class="knowledge-summary-icon blue" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />
              </svg>
            </span>
            <div>
              <small>知识条目</small>
              <strong>{{ knowledgeItems.length }}</strong>
              <span>项企业信息</span>
            </div>
          </article>
          <article class="knowledge-summary-card">
            <span class="knowledge-summary-icon violet" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <path d="M7 3h7l4 4v14H7zM14 3v5h5" />
              </svg>
            </span>
            <div>
              <small>资料文件</small>
              <strong>{{ documentMaterials.length }}</strong>
              <span>个资料 · {{ imageMaterials.length }} 张图片</span>
            </div>
          </article>
          <article class="knowledge-summary-card">
            <span class="knowledge-summary-icon cyan" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <circle cx="12" cy="12" r="8" />
                <path d="M12 8v4l3 2" />
              </svg>
            </span>
            <div>
              <small>最近更新</small>
              <strong class="knowledge-date">
                {{ latestUpdated ? formatDate(latestUpdated) : "暂无" }}
              </strong>
              <span>{{ representedCategories }} 个信息分类</span>
            </div>
          </article>
        </section>

        <section class="knowledge-import-layout">
          <article class="panel knowledge-import-card">
            <header class="knowledge-section-heading">
              <span class="knowledge-section-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                >
                  <path d="M12 16V4m0 0 4 4m-4-4L8 8M5 20h14" />
                </svg>
              </span>
              <div>
                <h2>资料导入</h2>
                <p>下载模板发给客户填写，收回后直接上传到企业知识库。</p>
              </div>
            </header>

            <ol class="knowledge-import-steps">
              <li>
                <span>1</span>
                <div>
                  <strong>下载模板</strong><small>发送给客户填写</small>
                </div>
              </li>
              <li>
                <span>2</span>
                <div>
                  <strong>收集资料</strong><small>补充现有介绍文件</small>
                </div>
              </li>
              <li>
                <span>3</span>
                <div>
                  <strong>上传导入</strong><small>系统整理为知识条目</small>
                </div>
              </li>
            </ol>

            <div class="knowledge-import-actions">
              <a
                class="button"
                href="/downloads/GEO客户资料采集表模板.xlsx"
                download
              >
                下载客户资料模板
              </a>
              <label class="button knowledge-file-button">
                选择资料文件
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.xlsx,.txt"
                  :disabled="uploadState === 'running'"
                  @change="chooseFiles"
                />
              </label>
              <button
                class="button primary"
                type="button"
                :disabled="
                  selectedFiles.length === 0 || uploadState === 'running'
                "
                @click="startUpload"
              >
                {{
                  uploadState === "running" ? "正在导入…" : "上传并导入知识库"
                }}
              </button>
            </div>

            <p v-if="selectedFiles.length" class="knowledge-selected-files">
              已选择：{{ selectedFiles.map((file) => file.name).join("、") }}
            </p>
            <p
              v-if="uploadState === 'succeeded'"
              class="state-success"
              role="status"
            >
              资料已上传，系统正在整理知识条目。
            </p>
            <p v-if="uploadState === 'failed'" class="state-error" role="alert">
              {{ uploadError }}
            </p>
          </article>

          <aside class="panel knowledge-catalog-card">
            <header class="knowledge-section-heading compact">
              <span class="knowledge-section-icon soft" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                >
                  <rect x="4" y="4" width="6" height="6" rx="1.5" />
                  <rect x="14" y="4" width="6" height="6" rx="1.5" />
                  <rect x="4" y="14" width="6" height="6" rx="1.5" />
                  <rect x="14" y="14" width="6" height="6" rx="1.5" />
                </svg>
              </span>
              <div>
                <h2>当前知识结构</h2>
                <p>已录入的信息会自动用于后续 AI 任务。</p>
              </div>
            </header>
            <div v-if="categoryCounts.length" class="knowledge-category-list">
              <span v-for="category in categoryCounts" :key="category.value">
                {{ category.label }}
                <strong>{{ category.count }}</strong>
              </span>
            </div>
            <p v-else class="knowledge-catalog-empty">
              上传客户资料或手工新增第一条企业信息。
            </p>
          </aside>
        </section>

        <section class="panel knowledge-image-library">
          <header class="panel-header">
            <div>
              <p class="eyebrow">企业素材</p>
              <h2>企业图片库</h2>
              <p>
                上传门店、环境、服务过程或作品图片。生成文章时会随机绑定最多 2
                张，一键发布时自动插入正文的合适段落。
              </p>
            </div>
            <div class="knowledge-image-actions">
              <label class="button knowledge-file-button">
                选择多张图片
                <input
                  type="file"
                  multiple
                  accept=".png,.jpg,.jpeg"
                  :disabled="imageUploadState === 'running'"
                  @change="chooseImageFiles"
                />
              </label>
              <button
                class="button primary"
                type="button"
                :disabled="
                  selectedImageFiles.length === 0 ||
                  imageUploadState === 'running'
                "
                @click="startImageUpload"
              >
                {{
                  imageUploadState === "running" ? "正在上传…" : "上传到图片库"
                }}
              </button>
            </div>
          </header>
          <p v-if="selectedImageFiles.length" class="knowledge-selected-files">
            已选择 {{ selectedImageFiles.length }} 张：{{
              selectedImageFiles.map((file) => file.name).join("、")
            }}
          </p>
          <p
            v-if="imageUploadState === 'succeeded'"
            class="state-success knowledge-image-state"
            role="status"
          >
            图片已加入企业图片库，后续生成和发布会自动使用。
          </p>
          <p
            v-if="imageUploadState === 'failed'"
            class="state-error knowledge-image-state"
            role="alert"
          >
            {{ imageUploadError }}
          </p>
          <div v-if="imageMaterials.length" class="knowledge-image-grid">
            <figure v-for="material in imageMaterials" :key="material.id">
              <img
                :src="material.file_url ?? materialFileUrl(material.id)"
                :alt="material.file_name"
                loading="lazy"
              />
              <figcaption>
                <div>
                  <strong>{{ material.file_name }}</strong>
                  <span>{{ formatDate(material.uploaded_at) }}</span>
                </div>
                <button
                  class="knowledge-image-delete"
                  type="button"
                  :aria-label="`删除图片 ${material.file_name}`"
                  title="删除图片"
                  @click="pendingDeleteImage = material"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    aria-hidden="true"
                  >
                    <path
                      d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5"
                    />
                  </svg>
                </button>
              </figcaption>
            </figure>
          </div>
          <div v-else class="knowledge-image-empty">
            <strong>还没有企业图片</strong>
            <span>建议至少上传 4 张，文章之间更容易形成不同的配图组合。</span>
          </div>
        </section>

        <section
          v-if="documentMaterials.length"
          class="panel knowledge-materials-card"
        >
          <header class="panel-header">
            <div>
              <h2>已导入资料</h2>
              <p>保留原始文件和处理状态，便于后续更新企业知识库。</p>
            </div>
            <span>{{ documentMaterials.length }} 个文件</span>
          </header>
          <div class="knowledge-material-list">
            <article v-for="material in documentMaterials" :key="material.id">
              <span class="knowledge-file-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                >
                  <path d="M7 3h7l4 4v14H7zM14 3v5h5" />
                </svg>
              </span>
              <div>
                <strong>{{ material.file_name }}</strong>
                <small>
                  {{ formatDate(material.uploaded_at) }} ·
                  {{ material.fragment_count }} 个内容片段
                </small>
              </div>
              <span
                class="knowledge-material-status"
                :data-status="material.extraction_status"
              >
                {{ materialStatus(material.extraction_status) }}
              </span>
            </article>
          </div>
        </section>

        <section class="panel knowledge-records-card">
          <header class="knowledge-records-head">
            <div>
              <p class="eyebrow">企业标准档案</p>
              <h2>知识条目</h2>
              <span>这些内容将作为 AI 生成文章时的企业信息依据。</span>
            </div>
            <button
              class="button primary"
              type="button"
              @click="openCreateEditor"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
              新增知识条目
            </button>
          </header>

          <div class="knowledge-record-toolbar">
            <label class="knowledge-search">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-4-4" />
              </svg>
              <input
                v-model="searchText"
                aria-label="搜索知识条目"
                placeholder="搜索标题或内容"
              />
            </label>
            <label class="knowledge-filter">
              <span class="sr-only">按分类筛选</span>
              <select v-model="categoryFilter" aria-label="按分类筛选">
                <option value="all">全部分类</option>
                <option
                  v-for="category in categories"
                  :key="category.value"
                  :value="category.value"
                >
                  {{ category.label }}
                </option>
              </select>
            </label>
          </div>

          <div v-if="filteredItems.length" class="knowledge-record-list">
            <article v-for="fact in filteredItems" :key="fact.id">
              <span class="knowledge-category-badge">
                {{ categoryLabel(fact.category) }}
              </span>
              <div class="knowledge-record-content">
                <strong>{{ fact.label }}</strong>
                <p>{{ fact.value }}</p>
                <small>更新于 {{ formatDate(fact.updated_at) }}</small>
              </div>
              <button
                class="button compact"
                type="button"
                :aria-label="`编辑${fact.label}`"
                @click="openEditEditor(fact)"
              >
                编辑
              </button>
            </article>
          </div>

          <div v-else class="knowledge-record-empty">
            <span aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
              >
                <path d="M5 4h14v16H5zM8 8h8M8 12h5" />
              </svg>
            </span>
            <h3>
              {{
                searchText || categoryFilter !== "all"
                  ? "没有符合条件的知识条目"
                  : "还没有知识条目"
              }}
            </h3>
            <p>
              {{
                searchText || categoryFilter !== "all"
                  ? "可以更换搜索词或查看全部分类。"
                  : "上传客户资料，或手工新增企业信息。"
              }}
            </p>
            <button
              v-if="!searchText && categoryFilter === 'all'"
              class="button primary"
              type="button"
              @click="openCreateEditor"
            >
              新增第一条知识
            </button>
          </div>
        </section>
      </template>
    </main>
  </AppShell>

  <ModalDialog
    v-if="pendingDeleteImage"
    title="删除企业图片"
    size="small"
    :close-disabled="imageDeleting"
    @close="pendingDeleteImage = null"
  >
    <div class="knowledge-delete-dialog">
      <img
        :src="
          pendingDeleteImage.file_url ?? materialFileUrl(pendingDeleteImage.id)
        "
        :alt="pendingDeleteImage.file_name"
      />
      <div>
        <strong>{{ pendingDeleteImage.file_name }}</strong>
        <p>
          删除后，文章中已绑定的这张图片也会同步移除，原始图片文件无法恢复。
        </p>
      </div>
    </div>
    <p v-if="imageDeleteError" class="state-error" role="alert">
      {{ imageDeleteError }}
    </p>
    <div class="dialog-actions">
      <button
        class="button"
        type="button"
        :disabled="imageDeleting"
        @click="pendingDeleteImage = null"
      >
        取消
      </button>
      <button
        class="button danger"
        type="button"
        :disabled="imageDeleting"
        @click="confirmDeleteImage"
      >
        {{ imageDeleting ? "正在删除…" : "确认删除" }}
      </button>
    </div>
  </ModalDialog>

  <ModalDialog
    v-if="editorOpen"
    :title="editingFact ? '编辑知识条目' : '新增知识条目'"
    size="small"
    @close="editorOpen = false"
  >
    <p class="knowledge-editor-tip">
      保存后立即更新企业知识库，后续 GEO 分析和 AI 内容生成会使用最新信息。
    </p>
    <label class="field">
      <span>信息分类</span>
      <select v-model="draftCategory" :disabled="Boolean(editingFact)">
        <option
          v-for="category in categories"
          :key="category.value"
          :value="category.value"
        >
          {{ category.label }}
        </option>
      </select>
    </label>
    <label class="field">
      <span>知识标题</span>
      <input
        v-model="draftLabel"
        placeholder="例如：核心服务、服务区域、适合人群"
      />
    </label>
    <label class="field">
      <span>详细内容</span>
      <textarea
        v-model="draftValue"
        rows="6"
        placeholder="完整填写企业的真实信息，便于 AI 准确理解和使用"
      />
    </label>
    <p v-if="factError" class="state-error" role="alert">{{ factError }}</p>
    <div class="dialog-actions">
      <button class="button" type="button" @click="editorOpen = false">
        取消
      </button>
      <button
        class="button primary"
        type="button"
        :disabled="factSaving || !draftLabel.trim() || !draftValue.trim()"
        @click="saveKnowledgeItem"
      >
        {{ factSaving ? "正在保存…" : "保存到知识库" }}
      </button>
    </div>
  </ModalDialog>

  <ModalDialog
    v-if="accountOpen"
    title="账户菜单"
    size="small"
    @close="accountOpen = false"
  >
    <p>账户操作将在客户工作台统一管理。</p>
    <RouterLink class="button" :to="{ name: 'clients', query: { clientId } }">
      返回客户工作台
    </RouterLink>
  </ModalDialog>
</template>
