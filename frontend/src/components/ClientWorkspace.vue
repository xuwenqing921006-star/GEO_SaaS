<script setup lang="ts">
/* eslint-disable vue/multiline-html-element-content-newline */
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  useRoute,
  useRouter,
} from "vue-router";
import {
  archiveClient,
  createClient,
  getClient,
  listClients,
  restoreClient,
  updateClient,
} from "../api/clients";
import type {
  ClientDetail,
  ClientFilters,
  ClientSummary,
  ClientsPage,
  CreateClientInput,
} from "../api/dto";
import { ApiError } from "../api/http";
import { useWorkspaceStore } from "../stores/workspace";
import CreateClientForm from "./CreateClientForm.vue";
import ModalDialog from "./ModalDialog.vue";

const route = useRoute();
const router = useRouter();
const workspace = useWorkspaceStore();
const emit = defineEmits<{ logout: [] }>();
const queryClient = useQueryClient();

const createOpen = ref(false);
const switchOpen = ref(false);
const viewOpen = ref(false);
const editOpen = ref(false);
const editCloseOpen = ref(false);
const deleteOpen = ref(false);
const toast = ref("");
const searchRef = ref<HTMLInputElement | null>(null);
const createRef = ref<HTMLButtonElement | null>(null);
const errors = ref<Record<string, string>>({});
const editErrors = ref<Record<string, string>>({});
const saveError = ref("");
const viewDetailError = ref("");
const editDetailError = ref("");
const detailPending = ref(false);
const editDetailPending = ref(false);
const editPending = ref(false);
const lifecycleError = ref("");
const lifecyclePending = ref(false);
const lifecycleMode = ref<"archive" | "restore">("archive");
const lifecycleTarget = ref<ClientSummary | null>(null);
const archiveReason = ref("");
const viewTarget = ref<ClientSummary | null>(null);
const detailClient = ref<ClientDetail | null>(null);
const editTarget = ref<ClientSummary | null>(null);
const editInitial = ref<CreateClientInput | null>(null);
const editVersion = ref(0);
const editDraft = ref<CreateClientInput | null>(null);
let syncingClientQuery = false;
let completingPendingNavigation = false;
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let viewRequestSequence = 0;
let editRequestSequence = 0;

if (typeof route.query.clientId === "string")
  workspace.currentClientId = route.query.clientId;

const filters = computed<ClientFilters>(() => {
  const q = route.query;
  const status =
    q.status === "active" || q.status === "paused" || q.status === "archived"
      ? q.status
      : "";
  return {
    q: typeof q.q === "string" ? q.q : "",
    status,
    sort: q.sort === "standard_name" ? "standard_name" : "-updated_at",
    page: Math.max(1, Number(q.page) || 1),
    page_size: [10, 20, 50, 100].includes(Number(q.page_size))
      ? Number(q.page_size)
      : 20,
  };
});
const clientsQuery = useQuery({
  queryKey: computed(() => ["clients", filters.value]),
  queryFn: () => listClients(filters.value),
});
const clientPage = computed(() => clientsQuery.data.value);
const clientsPending = computed(() => clientsQuery.isPending.value);
const clientsError = computed(() => clientsQuery.isError.value);
watch(
  [clientsQuery.data, () => route.query.clientId],
  ([page, queryId]) => {
    if (!page) return;
    const desired =
      typeof queryId === "string" &&
      page.items.some((item) => item.id === queryId)
        ? queryId
        : (page.items[0]?.id ?? "");
    workspace.setCurrentClient(
      page.items.find((item) => item.id === desired) ?? null,
    );
    if (desired && queryId !== desired) {
      syncingClientQuery = true;
      void router
        .replace({ query: { ...route.query, clientId: desired } })
        .finally(() => {
          syncingClientQuery = false;
        });
    }
  },
  { immediate: true },
);

const updateQuery = (
  patch: Record<string, string | number | undefined>,
  replace = false,
): void => {
  const next = {
    ...route.query,
    ...Object.fromEntries(
      Object.entries(patch)
        .filter(([, value]) => value !== undefined)
        .map(([key, value]) => [key, String(value)]),
    ),
  };
  if (replace) void router.replace({ query: next });
  else void router.push({ query: next });
};
const search = (value: string): void => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => updateQuery({ q: value, page: 1 }), 250);
};
const openCreate = (): void => {
  createRef.value?.focus();
  createOpen.value = true;
};
const closeCreate = (): void => {
  createOpen.value = false;
  void nextTick(() => createRef.value?.focus());
};
const selectClient = (id: string): void => {
  if (workspace.isDirty && id !== workspace.currentClientId) {
    openPendingNavigation({ type: "client", clientId: id });
    return;
  }
  updateQuery({ clientId: id });
};
const selectActionClient = (item: ClientSummary): void => {
  if (item.id === workspace.currentClientId) return;
  workspace.setCurrentClient(item);
  updateQuery({ clientId: item.id });
};

const taskDestination = (
  item: ClientSummary,
): {
  path:
    | "/knowledge"
    | "/diagnostics"
    | "/strategy"
    | "/content"
    | "/publishing"
    | "/channels"
    | "/monitoring";
  label: string;
} => {
  const task = item.next_action;
  if (/监测|复测|可见性/.test(task))
    return { path: "/monitoring", label: "AI 可见性监测" };
  if (/文章发布|发布文章/.test(task))
    return { path: "/publishing", label: "文章发布" };
  if (/渠道|账号|平台配置/.test(task))
    return { path: "/channels", label: "渠道配置" };
  if (/关键词|问题|计划|策略|简报/.test(task))
    return { path: "/strategy", label: "关键词" };
  if (/诊断/.test(task)) return { path: "/diagnostics", label: "GEO 诊断" };
  if (/内容|文章|生成|写作/.test(task))
    return { path: "/content", label: "内容工作台" };
  return { path: "/knowledge", label: "企业知识库" };
};
const goToTask = (item: ClientSummary): void => {
  if (workspace.isDirty && item.id !== workspace.currentClientId) {
    openPendingNavigation({
      type: "route",
      fullPath: `${taskDestination(item).path}?clientId=${item.id}`,
    });
    return;
  }
  workspace.setCurrentClient(item);
  void router.push({
    path: taskDestination(item).path,
    query: { clientId: item.id },
  });
};
const formatUpdatedAt = (value: string): string => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
};
const inputFromSummary = (item: ClientSummary): CreateClientInput => ({
  standard_name: item.standard_name,
  short_name: item.short_name,
  industry_code: item.industry_code,
  province: item.province,
  city: item.city,
  district: item.district,
  address: "",
  contact_phone: null,
  contact_wechat: null,
  business_hours: null,
  service_radius: null,
  cooperation_started_on: "",
  notes: null,
});
const inputFromDetail = (item: ClientDetail): CreateClientInput => ({
  standard_name: item.standard_name,
  short_name: item.short_name,
  industry_code: item.industry_code,
  province: item.province,
  city: item.city,
  district: item.district,
  address: item.address,
  contact_phone: item.contact_phone,
  contact_wechat: item.contact_wechat,
  business_hours: item.business_hours,
  service_radius: item.service_radius,
  cooperation_started_on: item.cooperation_started_on,
  notes: item.notes,
});
const isVisibleInCurrentFilter = (item: ClientSummary): boolean =>
  filters.value.status
    ? item.status === filters.value.status
    : item.status !== "archived";
const replaceClient = (updated: ClientSummary): void => {
  if (workspace.currentClientId === updated.id)
    workspace.setCurrentClient(updated);
  queryClient.setQueryData(
    ["clients", filters.value],
    (old: ClientsPage | undefined) => {
      if (!old) return old;
      const exists = old.items.some((item) => item.id === updated.id);
      const visible = isVisibleInCurrentFilter(updated);
      if (!visible) {
        const total = Math.max(0, old.total - (exists ? 1 : 0));
        return {
          ...old,
          items: old.items.filter((item) => item.id !== updated.id),
          total,
          has_next: old.page * old.page_size < total,
        };
      }
      const total = old.total + (exists ? 0 : 1);
      return {
        ...old,
        items: exists
          ? old.items.map((item) => (item.id === updated.id ? updated : item))
          : [updated, ...old.items].slice(0, old.page_size),
        total,
        has_next: old.page * old.page_size < total,
      };
    },
  );
};

const createMutation = useMutation({
  mutationFn: (input: CreateClientInput) => createClient(input),
  onSuccess: (created) => {
    errors.value = {};
    createOpen.value = false;
    toast.value = "客户创建成功";
    const defaultFilters: ClientFilters = {
      q: "",
      status: "",
      sort: "-updated_at",
      page: 1,
      page_size: 20,
    };
    queryClient.setQueryData(
      ["clients", defaultFilters],
      (old: ClientsPage | undefined) => {
        if (!old) return old;
        const exists = old.items.some((item) => item.id === created.id);
        const total = old.total + (exists ? 0 : 1);
        return {
          ...old,
          items: exists
            ? old.items.map((item) => (item.id === created.id ? created : item))
            : [created, ...old.items].slice(0, old.page_size),
          total,
          has_next: old.page * old.page_size < total,
        };
      },
    );
    void router.push({ query: { clientId: created.id } });
    void queryClient.invalidateQueries({ queryKey: ["clients"] });
    void nextTick(() => createRef.value?.focus());
  },
  onError: (error) => {
    const mapped =
      error instanceof ApiError
        ? Object.fromEntries(
            error.fieldErrors.map(({ field, message }) => [field, message]),
          )
        : {};
    errors.value = Object.keys(mapped).length
      ? mapped
      : { standard_name: "创建失败，请重试" };
  },
});
const creating = computed(() => createMutation.isPending.value);

const openView = async (item: ClientSummary): Promise<void> => {
  const requestSequence = ++viewRequestSequence;
  selectActionClient(item);
  viewTarget.value = item;
  detailClient.value = null;
  viewDetailError.value = "";
  detailPending.value = true;
  viewOpen.value = true;
  try {
    const detail = await getClient(item.id);
    if (
      requestSequence === viewRequestSequence &&
      viewOpen.value &&
      viewTarget.value?.id === item.id
    )
      detailClient.value = detail;
  } catch {
    if (requestSequence === viewRequestSequence)
      viewDetailError.value =
        "详细资料暂时无法读取，当前仍展示列表中的 GEO 进度。";
  } finally {
    if (requestSequence === viewRequestSequence) detailPending.value = false;
  }
};
const closeView = (): void => {
  viewRequestSequence += 1;
  viewOpen.value = false;
  detailPending.value = false;
  viewDetailError.value = "";
};
const beginEdit = async (item: ClientSummary): Promise<void> => {
  const requestSequence = ++editRequestSequence;
  selectActionClient(item);
  editTarget.value = item;
  editVersion.value = item.version;
  editInitial.value = inputFromSummary(item);
  editDraft.value = inputFromSummary(item);
  editErrors.value = {};
  editDetailError.value = "";
  editDetailPending.value = true;
  workspace.isDirty = false;
  editOpen.value = true;
  try {
    const detail = await getClient(item.id);
    if (
      requestSequence !== editRequestSequence ||
      !editOpen.value ||
      editTarget.value?.id !== item.id
    )
      return;
    const input = inputFromDetail(detail);
    editVersion.value = detail.version;
    editInitial.value = input;
    editDraft.value = input;
  } catch {
    if (requestSequence === editRequestSequence)
      editDetailError.value =
        "完整资料暂时无法读取；可稍后重试，当前已保留列表中的基础信息。";
  } finally {
    if (requestSequence === editRequestSequence)
      editDetailPending.value = false;
  }
};
const handleEditChange = (input: CreateClientInput): void => {
  editDraft.value = input;
};
const finishEdit = (): void => {
  editRequestSequence += 1;
  workspace.isDirty = false;
  editOpen.value = false;
  editCloseOpen.value = false;
  editTarget.value = null;
  editDraft.value = null;
  editErrors.value = {};
  editDetailError.value = "";
  editDetailPending.value = false;
  saveError.value = "";
};
const requestCloseEdit = (): void => {
  if (editPending.value) return;
  if (workspace.isDirty) {
    saveError.value = "";
    editCloseOpen.value = true;
    return;
  }
  finishEdit();
};
const persistEdit = async (input: CreateClientInput): Promise<boolean> => {
  const target = editTarget.value;
  if (!target) return false;
  editPending.value = true;
  editErrors.value = {};
  saveError.value = "";
  try {
    const updated = await updateClient(target.id, editVersion.value, input);
    if (editTarget.value?.id !== target.id) return false;
    replaceClient(updated);
    workspace.isDirty = false;
    toast.value = "客户资料已更新";
    return true;
  } catch (error) {
    const mapped =
      error instanceof ApiError
        ? Object.fromEntries(
            error.fieldErrors.map(({ field, message }) => [field, message]),
          )
        : {};
    editErrors.value = Object.keys(mapped).length
      ? mapped
      : { standard_name: "保存失败，请检查后重试" };
    saveError.value =
      error instanceof ApiError ? error.message : "保存失败，请重试";
    return false;
  } finally {
    editPending.value = false;
  }
};
const saveEdit = async (input: CreateClientInput): Promise<void> => {
  if (await persistEdit(input)) finishEdit();
};
const saveAndCloseEdit = async (): Promise<void> => {
  if (!editDraft.value) return;
  if (await persistEdit(editDraft.value)) finishEdit();
};
const discardAndCloseEdit = (): void => {
  if (!editPending.value) finishEdit();
};

const openArchive = (item: ClientSummary): void => {
  lifecycleTarget.value = item;
  archiveReason.value = "";
  lifecycleError.value = "";
  deleteOpen.value = true;
};
const lifecycleFailureMessage = (
  mode: "archive" | "restore",
  error: unknown,
): string => {
  if (error instanceof ApiError && error.status === 409) {
    if (mode === "archive" && error.message.includes("运行中任务"))
      return "客户存在运行中任务，暂时不能删除";
    return error.message;
  }
  return `${mode === "archive" ? "删除" : "恢复"}失败，请重试`;
};
const runLifecycle = async (
  mode: "archive" | "restore",
  item = lifecycleTarget.value,
): Promise<void> => {
  if (!item) return;
  lifecycleMode.value = mode;
  lifecycleTarget.value = item;
  lifecycleError.value = "";
  lifecyclePending.value = true;
  try {
    const updated =
      mode === "archive"
        ? await archiveClient(item.id, item.version, archiveReason.value)
        : await restoreClient(item.id, item.version);
    replaceClient(updated);
    void queryClient.invalidateQueries({
      queryKey: ["clients", filters.value],
    });
    if (
      workspace.currentClientId === item.id &&
      !isVisibleInCurrentFilter(updated)
    ) {
      const nextClient =
        clientPage.value?.items.find(
          (candidate) =>
            candidate.id !== item.id && isVisibleInCurrentFilter(candidate),
        ) ?? null;
      workspace.setCurrentClient(nextClient);
      void router.replace({
        query: {
          ...route.query,
          clientId: nextClient?.id,
        },
      });
    }
    deleteOpen.value = false;
    toast.value =
      mode === "archive" ? "客户已移入已删除状态，可随时恢复" : "客户已恢复";
  } catch (error) {
    lifecycleError.value = lifecycleFailureMessage(mode, error);
  } finally {
    lifecyclePending.value = false;
  }
};

const openPendingNavigation = (
  navigation: NonNullable<typeof workspace.pendingNavigation>,
): void => {
  if (editPending.value) return;
  workspace.pendingNavigation = navigation;
  workspace.pendingClientId =
    navigation.type === "client" ? navigation.clientId : "";
  saveError.value = "";
  switchOpen.value = true;
};
const cancelPendingNavigation = (): void => {
  if (editPending.value) return;
  switchOpen.value = false;
  saveError.value = "";
  workspace.pendingNavigation = null;
  workspace.pendingClientId = "";
};
const completePendingNavigation = (): void => {
  const pending = workspace.pendingNavigation;
  workspace.pendingNavigation = null;
  workspace.pendingClientId = "";
  switchOpen.value = false;
  if (!pending) return;
  if (pending.type === "client") {
    const clientId = pending.clientId;
    workspace.currentClientId = clientId;
    const nextClient = clientPage.value?.items.find(
      (item) => item.id === clientId,
    );
    if (nextClient) workspace.setCurrentClient(nextClient);
    completingPendingNavigation = true;
    void router.push({ query: { ...route.query, clientId } }).finally(() => {
      completingPendingNavigation = false;
    });
  } else if (pending.type === "route") {
    completingPendingNavigation = true;
    void router.push(pending.fullPath).finally(() => {
      completingPendingNavigation = false;
    });
  } else {
    emit("logout");
  }
};
const saveAndSwitch = async (): Promise<void> => {
  if (editPending.value || !editTarget.value || !editDraft.value) return;
  saveError.value = "";
  if (await persistEdit(editDraft.value)) {
    finishEdit();
    completePendingNavigation();
  }
};
const discard = (): void => {
  if (editPending.value) return;
  finishEdit();
  completePendingNavigation();
};
const requestLogout = (): void => {
  if (workspace.isDirty) {
    openPendingNavigation({ type: "logout" });
    return;
  }
  emit("logout");
};
const keyboard = (event: KeyboardEvent): void => {
  if (
    event.key === "/" &&
    !document.querySelector("[role=dialog]") &&
    !(event.target instanceof HTMLInputElement)
  ) {
    event.preventDefault();
    searchRef.value?.focus();
  }
};
const beforeUnload = (event: BeforeUnloadEvent): void => {
  if (workspace.isDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
};
onMounted(() => {
  window.addEventListener("keydown", keyboard);
  window.addEventListener("beforeunload", beforeUnload);
});
onUnmounted(() => {
  window.removeEventListener("keydown", keyboard);
  window.removeEventListener("beforeunload", beforeUnload);
});
const guardNavigation = (fullPath: string): boolean => {
  if (completingPendingNavigation || syncingClientQuery) return true;
  if (editPending.value) return false;
  if (!workspace.isDirty) return true;
  openPendingNavigation({ type: "route", fullPath });
  return false;
};
onBeforeRouteUpdate((to) => guardNavigation(to.fullPath));
onBeforeRouteLeave((to) => guardNavigation(to.fullPath));
defineExpose({ requestLogout });
</script>

<template>
  <main class="workspace clients-workspace" data-client="web">
    <div class="page-head">
      <div>
        <p class="eyebrow">客户组合</p>
        <h1>客户工作台</h1>
        <p>在一张列表中查看客户资料状态、当前任务和下一步操作。</p>
      </div>
      <button
        ref="createRef"
        class="button primary"
        type="button"
        aria-label="新建客户"
        @click="openCreate"
      >
        ＋ 新建客户
      </button>
    </div>

    <section class="toolbar" aria-label="客户筛选">
      <label class="search-field"
        ><span>搜索客户</span
        ><input
          ref="searchRef"
          :value="filters.q"
          type="search"
          role="searchbox"
          aria-label="搜索客户"
          placeholder="名称、地区或行业"
          @input="search(($event.target as HTMLInputElement).value)" /></label
      ><label
        ><span>状态</span
        ><select
          :value="filters.status"
          @change="
            updateQuery({
              status: ($event.target as HTMLSelectElement).value,
              page: 1,
            })
          "
        >
          <option value="">在管客户</option>
          <option value="active">活跃</option>
          <option value="paused">暂停</option>
          <option value="archived">已删除（可恢复）</option>
        </select></label
      ><label
        ><span>排序</span
        ><select
          :value="filters.sort"
          @change="
            updateQuery({ sort: ($event.target as HTMLSelectElement).value })
          "
        >
          <option value="-updated_at">最近更新</option>
          <option value="standard_name">企业名称</option>
        </select></label
      ><label
        ><span>每页</span
        ><select
          :value="filters.page_size"
          @change="
            updateQuery({
              page_size: ($event.target as HTMLSelectElement).value,
              page: 1,
            })
          "
        >
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select></label
      >
    </section>

    <section class="work-grid">
      <article class="panel list-panel">
        <header class="panel-header">
          <div>
            <h2>客户与 GEO 任务</h2>
            <p>优先处理有阻断、资料不完整的客户</p>
          </div>
          <span>{{ clientPage?.total ?? 0 }} 个客户</span>
        </header>
        <p
          v-if="clientsPending"
          class="state-line"
          role="status"
          aria-label="正在加载客户"
        >
          正在加载客户…
        </p>
        <div v-else-if="clientsError" class="state-error" role="alert">
          客户列表暂时不可用
          <button class="button" @click="clientsQuery.refetch()">重试</button>
        </div>
        <p v-else-if="!clientPage?.items.length" class="state-line">暂无客户</p>
        <div v-else class="table-scroll client-table-scroll">
          <table class="client-table">
            <caption class="sr-only">
              客户资料状态与操作列表
            </caption>
            <thead>
              <tr>
                <th scope="col">客户</th>
                <th scope="col">资料状态</th>
                <th scope="col">当前任务</th>
                <th scope="col">状态与更新</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in clientPage?.items ?? []" :key="item.id">
                <td class="client-identity-cell">
                  <button
                    class="client-name-button"
                    type="button"
                    :aria-label="`选择${item.standard_name}`"
                    :aria-pressed="item.id === workspace.currentClientId"
                    @click="selectClient(item.id)"
                  >
                    <span class="client-avatar" aria-hidden="true">{{
                      item.standard_name.slice(0, 1)
                    }}</span>
                    <span>
                      <strong>{{ item.standard_name }}</strong>
                      <small
                        >{{ item.city }}{{ item.district }} ·
                        {{ item.industry_name }}</small
                      >
                    </span>
                  </button>
                </td>
                <td>
                  <div class="client-progress">
                    <div>
                      <strong>{{ item.fact_completeness }}%</strong>
                      <span class="level-route">{{
                        item.fact_completeness >= 60
                          ? "可开始 GEO 工作"
                          : "建议继续完善"
                      }}</span>
                    </div>
                    <span class="progress-track" aria-hidden="true"
                      ><span
                        class="progress-fill"
                        :style="{ width: `${item.fact_completeness}%` }"
                    /></span>
                    <small>企业资料完整度</small>
                  </div>
                </td>
                <td class="task-cell">
                  <strong>{{ item.next_action }}</strong>
                  <span
                    class="task-blocker"
                    :class="{ clear: !item.blocking_issue_count }"
                    >{{
                      item.blocking_issue_count
                        ? `${item.blocking_issue_count} 项需关注`
                        : "状态正常"
                    }}</span
                  >
                  <button
                    class="task-link"
                    type="button"
                    :aria-label="`继续处理${item.standard_name}`"
                    @click="goToTask(item)"
                  >
                    进入{{ taskDestination(item).label }} →
                  </button>
                </td>
                <td>
                  <span class="status-badge" :data-status="item.status">
                    {{
                      item.status === "active"
                        ? "活跃"
                        : item.status === "paused"
                          ? "暂停"
                          : "已删除"
                    }}
                  </span>
                  <small class="updated-at"
                    >更新于 {{ formatUpdatedAt(item.updated_at) }}</small
                  >
                </td>
                <td>
                  <div class="row-actions">
                    <button
                      class="row-action"
                      type="button"
                      :aria-label="`查看${item.standard_name}`"
                      @click="openView(item)"
                    >
                      查看</button
                    ><button
                      v-if="item.status !== 'archived'"
                      class="row-action"
                      type="button"
                      :aria-label="`编辑${item.standard_name}`"
                      @click="beginEdit(item)"
                    >
                      编辑</button
                    ><button
                      v-if="item.status !== 'archived'"
                      class="row-action row-action--danger"
                      type="button"
                      :aria-label="`删除${item.standard_name}`"
                      @click="openArchive(item)"
                    >
                      删除</button
                    ><button
                      v-else
                      class="row-action row-action--restore"
                      type="button"
                      :aria-label="`恢复${item.standard_name}`"
                      :disabled="lifecyclePending"
                      @click="runLifecycle('restore', item)"
                    >
                      恢复
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <footer class="pagination">
          <button
            class="button"
            :disabled="filters.page === 1"
            @click="updateQuery({ page: filters.page - 1 })"
          >
            上一页</button
          ><span>第 {{ filters.page }} 页</span
          ><button
            class="button"
            :disabled="!clientPage?.has_next"
            @click="updateQuery({ page: filters.page + 1 })"
          >
            下一页
          </button>
        </footer>
      </article>
    </section>

    <p
      v-if="!deleteOpen && lifecycleError"
      class="state-error lifecycle-error"
      role="alert"
    >
      {{ lifecycleError }}
      <button
        class="button"
        :disabled="lifecyclePending"
        @click="runLifecycle(lifecycleMode)"
      >
        重试
      </button>
    </p>
    <p v-if="toast" class="toast" role="status">{{ toast }}</p>

    <ModalDialog v-if="createOpen" title="新建客户" @close="closeCreate">
      <CreateClientForm
        :submitting="creating"
        :server-errors="errors"
        @submit="createMutation.mutate"
        @cancel="closeCreate"
      />
    </ModalDialog>

    <ModalDialog
      v-if="viewOpen && viewTarget"
      :title="`查看客户 · ${viewTarget.standard_name}`"
      size="large"
      @close="closeView"
    >
      <section class="client-overview">
        <div class="overview-hero">
          <span class="client-avatar client-avatar--large" aria-hidden="true">{{
            viewTarget.standard_name.slice(0, 1)
          }}</span>
          <div>
            <h3>{{ viewTarget.standard_name }}</h3>
            <p>
              {{ viewTarget.province }} · {{ viewTarget.city }} ·
              {{ viewTarget.district }} · {{ viewTarget.industry_name }}
            </p>
          </div>
          <span class="status-badge" :data-status="viewTarget.status">{{
            viewTarget.status === "active"
              ? "活跃"
              : viewTarget.status === "paused"
                ? "暂停"
                : "已删除"
          }}</span>
        </div>
        <div class="overview-metrics">
          <article>
            <span>资料完整度</span
            ><strong>{{ viewTarget.fact_completeness }}%</strong>
          </article>
          <article>
            <span>当前阶段</span
            ><strong>{{ taskDestination(viewTarget).label }}</strong>
          </article>
          <article>
            <span>待关注事项</span
            ><strong>{{ viewTarget.blocking_issue_count }} 项</strong>
          </article>
        </div>
        <article class="overview-task">
          <div>
            <span>当前任务</span>
            <h3>{{ viewTarget.next_action }}</h3>
            <p>
              前往{{
                taskDestination(viewTarget).label
              }}继续处理，完成后列表会自动同步最新状态。
            </p>
          </div>
          <button class="button primary" @click="goToTask(viewTarget)">
            继续处理
          </button>
        </article>
        <p v-if="detailPending" class="state-line">正在读取客户详细资料…</p>
        <p v-if="viewDetailError" class="form-alert">
          {{ viewDetailError }}
        </p>
        <dl v-if="detailClient" class="overview-details">
          <div>
            <dt>详细地址</dt>
            <dd>{{ detailClient.address || "未填写" }}</dd>
          </div>
          <div>
            <dt>联系电话</dt>
            <dd>{{ detailClient.contact_phone || "未填写" }}</dd>
          </div>
          <div>
            <dt>联系微信</dt>
            <dd>{{ detailClient.contact_wechat || "未填写" }}</dd>
          </div>
          <div>
            <dt>营业时间</dt>
            <dd>{{ detailClient.business_hours || "未填写" }}</dd>
          </div>
          <div>
            <dt>服务范围</dt>
            <dd>{{ detailClient.service_radius || "未填写" }}</dd>
          </div>
          <div>
            <dt>合作开始</dt>
            <dd>{{ detailClient.cooperation_started_on || "未填写" }}</dd>
          </div>
        </dl>
      </section>
    </ModalDialog>

    <ModalDialog
      v-if="editOpen && editTarget"
      :title="`编辑客户 · ${editTarget.standard_name}`"
      size="large"
      :close-disabled="editPending"
      @close="requestCloseEdit"
    >
      <p v-if="editDetailError" class="form-alert">
        {{ editDetailError }}
      </p>
      <p v-if="editDetailPending" class="state-line" role="status">
        正在读取完整客户资料…
      </p>
      <CreateClientForm
        v-else
        mode="edit"
        :initial-value="editInitial"
        :submitting="editPending"
        :server-errors="editErrors"
        @dirty="workspace.isDirty = true"
        @change="handleEditChange"
        @submit="saveEdit"
        @cancel="requestCloseEdit"
      />
    </ModalDialog>

    <ModalDialog
      v-if="editCloseOpen"
      title="未保存的客户资料"
      size="small"
      :close-disabled="editPending"
      @close="editCloseOpen = false"
    >
      <div class="confirm-modal-content">
        <p>你修改了客户资料，直接关闭会丢失这些更改。</p>
        <p v-if="saveError" class="state-error" role="alert">
          {{ saveError }}
        </p>
        <footer class="modal-actions">
          <button
            class="button"
            type="button"
            :disabled="editPending"
            @click="editCloseOpen = false"
          >
            继续编辑</button
          ><button
            class="button danger"
            type="button"
            :disabled="editPending"
            @click="discardAndCloseEdit"
          >
            放弃修改</button
          ><button
            class="button primary"
            type="button"
            :disabled="editPending"
            @click="saveAndCloseEdit"
          >
            {{ editPending ? "正在保存…" : "保存修改并关闭" }}
          </button>
        </footer>
      </div>
    </ModalDialog>

    <ModalDialog
      v-if="deleteOpen && lifecycleTarget"
      :title="`删除客户 · ${lifecycleTarget.standard_name}`"
      size="small"
      @close="deleteOpen = false"
    >
      <div class="delete-modal-content">
        <section class="delete-confirmation">
          <span class="delete-confirmation__icon" aria-hidden="true">!</span>
          <div>
            <h3>确认从日常工作区移除这个客户？</h3>
            <p>
              本次删除可恢复。企业资料、生成文章、渠道配置和监测历史都不会被清除。
            </p>
          </div>
        </section>
        <label class="field"
          ><span>删除原因</span
          ><input
            v-model="archiveReason"
            aria-label="删除原因"
            placeholder="例如：合作暂停"
        /></label>
        <p v-if="lifecycleError" class="state-error" role="alert">
          {{ lifecycleError }}
          <button
            class="button"
            :disabled="lifecyclePending"
            @click="runLifecycle('archive')"
          >
            重试
          </button>
        </p>
        <footer class="modal-actions">
          <button class="button" type="button" @click="deleteOpen = false">
            取消</button
          ><button
            class="button danger"
            :disabled="!archiveReason || lifecyclePending"
            @click="runLifecycle('archive')"
          >
            {{ lifecyclePending ? "正在删除…" : "确认删除" }}
          </button>
        </footer>
      </div>
    </ModalDialog>

    <ModalDialog
      v-if="switchOpen"
      title="未保存的更改"
      size="small"
      :close-disabled="editPending"
      @close="cancelPendingNavigation"
    >
      <p>当前客户的资料修改尚未保存。</p>
      <p v-if="saveError" class="state-error" role="alert">{{ saveError }}</p>
      <footer class="modal-actions">
        <button
          class="button primary"
          :disabled="editPending"
          @click="saveAndSwitch"
        >
          {{
            workspace.pendingNavigation?.type === "logout"
              ? "保存并退出"
              : "保存并切换"
          }}</button
        ><button
          v-if="saveError"
          class="button"
          :disabled="editPending"
          @click="saveAndSwitch"
        >
          重试</button
        ><button class="button danger" :disabled="editPending" @click="discard">
          {{
            workspace.pendingNavigation?.type === "logout"
              ? "放弃并退出"
              : "放弃并切换"
          }}</button
        ><button
          class="button"
          :disabled="editPending"
          @click="cancelPendingNavigation"
        >
          取消
        </button>
      </footer>
    </ModalDialog>
  </main>
</template>
