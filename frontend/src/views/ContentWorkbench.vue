<script setup lang="ts">
import { useMutation, useQuery } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import type {
  ContentDocumentData,
  ContentFormCode,
  ContentGenerationTaskData,
  PublishingAccountData,
} from "../api/dto";
import { getChannels, getPublishingChannels } from "../api/channels";
import {
  confirmContentGenerationTask,
  createDocumentBatch,
  deleteDocument,
  getContentGenerationTask,
  getContentGenerationTasks,
  getDocument,
  getDocuments,
  publishDocument,
  runDocumentOperation,
  saveDocument,
} from "../api/content";
import {
  formatJobProgress,
  PUBLISHING_JOB_POLLING_INTERVAL,
  pollJobUntilTerminal,
  STANDARD_JOB_POLLING_INTERVAL,
} from "../api/jobPolling";
import { getLatestDiagnostic, materialFileUrl } from "../api/knowledge";
import { getPromptTemplates } from "../api/prompts";
import { getJob, getStrategy } from "../api/strategy";
import ModalDialog from "../components/ModalDialog.vue";
import {
  canRecordPublication,
  contentDocumentsRefetchInterval,
  contentGenerationAvailability,
  documentPublishableChannelIds,
  filterPublicationDocuments,
  plannedContentCount,
  type PublicationBucket,
  toggleAllKeywordSelection,
} from "../contentWorkbenchLogic";
import {
  ARTICLE_COVER_STYLES,
  articleCoverUrl,
  type ArticleCoverStyle,
} from "../articleCoverLogic";
import {
  notifyRequestError,
  notifyRequestSuccess,
} from "../requestNotifications";

const props = withDefaults(
  defineProps<{
    clientId: string;
    clientName: string;
    mode?: "generation" | "publishing";
  }>(),
  { mode: "generation" },
);
const emit = defineEmits<{
  "publishing-state": [
    state: {
      selectedCount: number;
      isPublishing: boolean;
      visible: boolean;
    },
  ];
}>();
const router = useRouter();
const isGenerationMode = computed(() => props.mode === "generation");
const isPublishingMode = computed(() => props.mode === "publishing");
const activeTrackedJobCount = ref(0);
const pendingBatchDocumentIds = ref<string[]>([]);
const knownPublicationStatuses = new Map<string, string>();
const knownGenerationTaskStatuses = new Map<string, string>();
const strategyQuery = useQuery({
  queryKey: ["strategy", props.clientId],
  queryFn: () => getStrategy(props.clientId),
  enabled: isGenerationMode,
});
const diagnosticQuery = useQuery({
  queryKey: ["diagnostic", props.clientId],
  queryFn: () => getLatestDiagnostic(props.clientId),
  enabled: isGenerationMode,
});
const documentsQuery = useQuery({
  queryKey: ["documents", props.clientId],
  queryFn: () => getDocuments(props.clientId),
  refetchInterval: (query) =>
    activeTrackedJobCount.value > 0
      ? false
      : contentDocumentsRefetchInterval(query.state.data?.items),
});
const promptsQuery = useQuery({
  queryKey: ["prompt-templates", "content-form"],
  queryFn: () => getPromptTemplates(),
});
const channelsQuery = useQuery({
  queryKey: ["channels", "content-generation"],
  queryFn: getChannels,
});
const publishingChannelsQuery = useQuery({
  queryKey: ["publishing-channels"],
  queryFn: getPublishingChannels,
});
const generationTasksQuery = useQuery({
  queryKey: ["content-generation-tasks", props.clientId],
  queryFn: () => getContentGenerationTasks(props.clientId),
  enabled: isGenerationMode,
  refetchInterval: (query) =>
    (query.state.data?.items ?? []).some((task) =>
      ["queued", "generating"].includes(task.status),
    )
      ? 6_000
      : false,
});
const articleCount = ref(5);
const articleLength = ref<"short" | "medium" | "long">("medium");
const contentFormCodes = ref<ContentFormCode[]>([]);
const selectedKeywordIds = ref<string[]>([]);
const targetChannelIds = ref<string[]>([]);
const actionError = ref("");
const actionMessage = ref("");
const selectedDocument = ref<ContentDocumentData | null>(null);
const detailLoading = ref(false);
const isEditing = ref(false);
const draftTitle = ref("");
const draftBody = ref("");
const regenerationSuggestion = ref("");
const regenerationChannelId = ref("");
const regenerationProgress = ref("");
const regenerationCompletedMessage = ref("");
const publishingDocumentIds = ref<string[]>([]);
const selectedPublicationDocumentIds = ref<string[]>([]);
const publicationView = ref<PublicationBucket>("unpublished");
const articleKeywordFilter = ref("");
const articleTypeFilter = ref("all");
const articleChannelFilter = ref("all");
const articleCoverStyle = ref<ArticleCoverStyle>("azure");
const articleCoverFailed = ref(false);
const selectedGenerationTask = ref<ContentGenerationTaskData | null>(null);
const generationTaskDetailLoading = ref(false);
const deleteTaskDocumentTarget = ref<ContentDocumentData | null>(null);

watch(publicationView, () => {
  selectedPublicationDocumentIds.value = [];
});

watch(actionMessage, (message) => {
  if (message) notifyRequestSuccess("内容操作完成", message);
});
watch(actionError, (message) => {
  if (message) notifyRequestError("内容操作未完成", message);
});
watch(
  () => documentsQuery.data.value?.items,
  (documents) => {
    if (!documents || !pendingBatchDocumentIds.value.length) return;
    const pendingIds = new Set(pendingBatchDocumentIds.value);
    const batchDocuments = documents.filter((document) =>
      pendingIds.has(document.id),
    );
    if (batchDocuments.length !== pendingIds.size) return;
    if (
      batchDocuments.some((document) =>
        ["pending", "generating"].includes(document.generation_status),
      )
    )
      return;
    const failed = batchDocuments.filter(
      (document) => document.generation_status === "failed",
    ).length;
    actionMessage.value = failed
      ? `文章生成结束：成功 ${batchDocuments.length - failed} 篇，失败 ${failed} 篇`
      : `${batchDocuments.length} 篇文章已全部生成完成`;
    if (failed) actionError.value = "部分文章生成失败，可重新选择关键词生成";
    pendingBatchDocumentIds.value = [];
  },
);
watch(
  () => generationTasksQuery.data.value?.items,
  async (tasks) => {
    if (!tasks) return;
    let shouldRefreshDocuments = false;
    for (const task of tasks) {
      const previous = knownGenerationTaskStatuses.get(task.id);
      knownGenerationTaskStatuses.set(task.id, task.status);
      if (!previous || previous === task.status) continue;
      if (["completed", "partial", "failed"].includes(task.status)) {
        shouldRefreshDocuments = true;
        if (task.status === "completed")
          notifyRequestSuccess(
            "文章生成完成",
            `本次 ${task.total_count} 篇文章已全部生成`,
          );
        else
          notifyRequestError(
            "文章生成结束",
            `成功 ${task.completed_count} 篇，失败 ${task.failed_count} 篇`,
          );
      }
    }
    if (shouldRefreshDocuments) await documentsQuery.refetch();
  },
  { immediate: true },
);
watch(
  () => documentsQuery.data.value?.items,
  (documents) => {
    if (!documents) return;
    for (const document of documents) {
      const previous = knownPublicationStatuses.get(document.id);
      const current = document.publication_status;
      knownPublicationStatuses.set(document.id, current);
      if (previous !== "pending_review") continue;
      if (current === "published")
        notifyRequestSuccess("平台审核通过", `《${document.title}》已发布成功`);
      if (current === "failed")
        notifyRequestError(
          "平台审核未通过",
          document.publication_error ?? `《${document.title}》发布失败`,
        );
    }
  },
  { immediate: true },
);

const trackContentJobs = async <T,>(
  operation: () => Promise<T>,
): Promise<T> => {
  activeTrackedJobCount.value += 1;
  try {
    return await operation();
  } finally {
    activeTrackedJobCount.value = Math.max(0, activeTrackedJobCount.value - 1);
  }
};

const officialKeywords = computed(() =>
  (strategyQuery.data.value?.items ?? []).filter(
    (item) => item.kind === "keyword" && item.active,
  ),
);
const selectedKeywords = computed(() => {
  const selected = new Set(selectedKeywordIds.value);
  return officialKeywords.value.filter((item) => selected.has(item.id));
});
const areAllKeywordsSelected = computed(() => {
  const selectableIds = officialKeywords.value
    .slice(0, 20)
    .map((item) => item.id);
  const selectedIds = new Set(selectedKeywordIds.value);
  return (
    selectableIds.length > 0 && selectableIds.every((id) => selectedIds.has(id))
  );
});
const toggleAllKeywords = (): void => {
  selectedKeywordIds.value = toggleAllKeywordSelection(
    officialKeywords.value.map((item) => item.id),
    selectedKeywordIds.value,
  );
};
const contentFormTemplates = computed(() =>
  (promptsQuery.data.value?.items ?? []).filter(
    (item) => item.category === "content_form" && item.active,
  ),
);
const targetChannels = computed(() =>
  (publishingChannelsQuery.data.value?.items ?? []).map((item) => {
    const selectable = item.accounts.some(
      (account) => account.enabled && account.connection_status === "connected",
    );
    return {
      ...item,
      selectable,
      unavailable_reason: item.account_count
        ? "账号未连接或未启用"
        : "尚未配置账号",
    };
  }),
);
const selectedChannels = computed(() =>
  targetChannels.value.filter((item) =>
    targetChannelIds.value.includes(item.id),
  ),
);
const selectedChannelSummary = computed(() => {
  if (!selectedChannels.value.length) return "请选择已配置平台";
  if (selectedChannels.value.length <= 2)
    return selectedChannels.value.map((item) => item.name).join("、");
  return `${selectedChannels.value
    .slice(0, 2)
    .map((item) => item.name)
    .join("、")} 等 ${selectedChannels.value.length} 个渠道`;
});
const plannedArticleCount = computed(() =>
  plannedContentCount(articleCount.value, selectedChannels.value.length),
);
const contentFormName = (code: string | null | undefined): string =>
  contentFormTemplates.value.find((item) => item.code === code)?.name ??
  code ??
  "历史默认";
const channelName = (channelId: string | null | undefined): string =>
  targetChannels.value.find((item) => item.id === channelId)?.name ??
  channelId ??
  "暂未指定";
const documents = computed(() => documentsQuery.data.value?.items ?? []);
const generationTasks = computed(
  () => generationTasksQuery.data.value?.items ?? [],
);
const visibleDocuments = computed(() =>
  filterPublicationDocuments(documents.value, {
    bucket: publicationView.value,
    keyword: "",
    keywordType: "all",
    channelId: "all",
  }),
);
const filteredDocuments = computed(() =>
  filterPublicationDocuments(documents.value, {
    bucket: publicationView.value,
    keyword: articleKeywordFilter.value,
    keywordType: articleTypeFilter.value,
    channelId: articleChannelFilter.value,
  }),
);
const publicationCounts = computed<Record<PublicationBucket, number>>(() => ({
  unpublished: filterPublicationDocuments(documents.value, {
    bucket: "unpublished",
    keyword: "",
    keywordType: "all",
    channelId: "all",
  }).length,
  published: filterPublicationDocuments(documents.value, {
    bucket: "published",
    keyword: "",
    keywordType: "all",
    channelId: "all",
  }).length,
  failed: filterPublicationDocuments(documents.value, {
    bucket: "failed",
    keyword: "",
    keywordType: "all",
    channelId: "all",
  }).length,
}));
const visibleDocumentsPending = computed(() => documentsQuery.isPending.value);
const visibleDocumentsError = computed(() => documentsQuery.isError.value);
const enabledPublishingAccounts = computed(() =>
  (publishingChannelsQuery.data.value?.items ?? []).flatMap((channel) =>
    channel.accounts
      .filter(
        (account) =>
          account.enabled && account.connection_status === "connected",
      )
      .map((account) => ({ ...account, platform_name: channel.name })),
  ),
);
const publishableAccountsFor = (
  document: ContentDocumentData,
): Array<PublishingAccountData & { platform_name: string }> => {
  const channels = new Set(documentPublishableChannelIds(document));
  return enabledPublishingAccounts.value.filter((account) => {
    if (!channels.has(account.channel_id)) return false;
    const targetVersionId =
      document.current_version?.target_channel_id === account.channel_id
        ? document.current_version.id
        : document.channel_variants.find(
            (item) => item.channel_id === account.channel_id,
          )?.version_id;
    return !(document.publications ?? []).some(
      (publication) =>
        publication.publishing_account_id === account.id &&
        publication.document_version_id === targetVersionId &&
        ["queued", "publishing", "pending_review", "published"].includes(
          publication.status,
        ),
    );
  });
};
const canOneClickPublish = (document: ContentDocumentData): boolean =>
  canRecordPublication(document) &&
  !["queued", "publishing", "pending_review"].includes(
    document.publication_status,
  ) &&
  publishableAccountsFor(document).length > 0;
const selectablePublicationDocuments = computed(() =>
  filteredDocuments.value.filter(canOneClickPublish),
);
const allVisiblePublicationDocumentsSelected = computed(
  () =>
    selectablePublicationDocuments.value.length > 0 &&
    selectablePublicationDocuments.value.every((document) =>
      selectedPublicationDocumentIds.value.includes(document.id),
    ),
);
const selectedPublicationDocuments = computed(() => {
  const selected = new Set(selectedPublicationDocumentIds.value);
  return documents.value.filter((document) => selected.has(document.id));
});
watch(
  () => ({
    selectedCount: selectedPublicationDocuments.value.length,
    isPublishing: publishingDocumentIds.value.length > 0,
    visible: publicationView.value === "unpublished",
  }),
  (state) => emit("publishing-state", state),
  { immediate: true },
);
const strategyOutdated = computed(
  () =>
    Boolean(strategyQuery.data.value) &&
    Boolean(diagnosticQuery.data.value) &&
    strategyQuery.data.value?.diagnostic_run_id !==
      diagnosticQuery.data.value?.id,
);
const generationAvailability = computed(() =>
  contentGenerationAvailability({
    selectedKeywordCount: selectedKeywords.value.length,
    diagnosticStale: diagnosticQuery.data.value?.is_stale === true,
    strategyOutdated: strategyOutdated.value,
    contentFormTemplateCount: contentFormTemplates.value.length,
    promptsPending: promptsQuery.isPending.value,
    channelsPending: channelsQuery.isPending.value,
    batchPending: batchMutation.isPending.value,
  }),
);
const generationLimitError = computed(() =>
  plannedArticleCount.value > 100
    ? "本次将生成超过 100 篇文章，请减少每个平台篇数或发布平台"
    : "",
);
const generationConfigurationError = computed(() => {
  if (!selectedKeywords.value.length) return "请至少选择 1 个正式关键词";
  if (!targetChannelIds.value.length)
    return "请至少选择 1 个已配置的自媒体平台";
  if (!contentFormCodes.value.length) return "请至少选择 1 种内容形式";
  return "";
});
const canGenerate = computed(
  () =>
    generationAvailability.value.enabled &&
    !generationLimitError.value &&
    !generationConfigurationError.value,
);

const contentStatusLabel = (document: ContentDocumentData): string => {
  if (document.generation_status === "pending") return "等待生成";
  if (document.generation_status === "generating") return "AI 生成中";
  if (document.generation_status === "failed") return "生成失败";
  if (
    document.status === "blocked" ||
    document.latest_check?.overall_status === "blocked"
  )
    return "需调整";
  return "可发布";
};
const contentStatusTone = (document: ContentDocumentData): string => {
  if (document.generation_status === "pending") return "pending";
  if (document.generation_status === "generating") return "generating";
  if (document.generation_status === "failed") return "failed";
  if (
    document.status === "blocked" ||
    document.latest_check?.overall_status === "blocked"
  )
    return "blocked";
  return "ready";
};
const publicationStatusLabel: Record<
  ContentDocumentData["publication_status"],
  string
> = {
  unpublished: "未发布",
  queued: "等待发布",
  publishing: "发布中",
  pending_review: "平台审核中",
  published: "已发布",
  failed: "发布失败",
  needs_login: "需要登录",
  needs_verification: "需要验证",
  rejected: "平台拒绝",
};
const publicationStatusText = (document: ContentDocumentData): string =>
  document.publication_status === "published" &&
  !document.current_version_published
    ? "当前版本未发布"
    : publicationStatusLabel[document.publication_status];
const publicationStatusTone = (document: ContentDocumentData): string =>
  document.publication_status === "published" &&
  !document.current_version_published
    ? "unpublished"
    : document.publication_status;
const keywordTypeLabel: Record<string, string> = {
  local_service: "地区主营",
  brand: "企业品牌",
  recommendation: "推荐决策",
  scenario: "场景适配",
  service_detail: "服务细分",
  comparison: "选择比较",
  transaction: "费用流程",
  trust: "信任核验",
};
const titleCandidateTypeLabel: Record<string, string> = {
  professional: "专业知识",
  scenario: "场景切入",
  local_decision: "本地决策",
  qa: "自然问答",
  brand_verification: "品牌核验",
  custom: "当前标题",
};
const qualityCategoryLabel: Record<string, string> = {
  fact_consistency: "企业事实",
  question_relevance: "关键词相关性",
  entity_clarity: "企业识别",
  answer_extractability: "答案可提取",
  source_traceability: "信息可追溯",
  natural_language: "自然表达",
  channel_fit: "渠道适配",
  compliance: "平台合规",
  duplicate_content: "内容重复",
  platform_low_quality: "平台低质风险",
};
const channelNamesById = computed<Record<string, string>>(() =>
  Object.fromEntries(
    (channelsQuery.data.value?.items ?? []).map((item) => [item.id, item.name]),
  ),
);
const suitableChannelNames = (document: ContentDocumentData): string[] =>
  documentPublishableChannelIds(document)
    .map((id) => channelNamesById.value[id] ?? id)
    .slice(0, 3);
const blockingFindings = (document: ContentDocumentData) =>
  (document.latest_check?.findings ?? []).filter(
    (finding) => finding.severity === "blocking",
  );
const blockingFindingCount = (document: ContentDocumentData): number =>
  blockingFindings(document).length;
const formatDateTime = (value: string): string =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
const generationTaskStatusLabel: Record<
  ContentGenerationTaskData["status"],
  string
> = {
  queued: "等待生成",
  generating: "生成中",
  completed: "已生成",
  partial: "部分失败",
  failed: "生成失败",
};
const taskKeywordSummary = (task: ContentGenerationTaskData): string =>
  task.keyword_snapshots.map((item) => item.text).join("、");
const taskChannelSummary = (task: ContentGenerationTaskData): string =>
  task.channel_ids.map((item) => channelName(item)).join("、");
const taskContentFormSummary = (task: ContentGenerationTaskData): string =>
  task.content_form_codes.map((item) => contentFormName(item)).join("、");
const isContentFormSelected = (code: string): boolean =>
  contentFormCodes.value.includes(code as ContentFormCode);
const toggleContentForm = (code: string): void => {
  const value = code as ContentFormCode;
  contentFormCodes.value = isContentFormSelected(code)
    ? contentFormCodes.value.filter((item) => item !== value)
    : [...contentFormCodes.value, value];
};

const batchMutation = useMutation({
  mutationFn: () =>
    createDocumentBatch(props.clientId, {
      keyword_ids: selectedKeywords.value.map((item) => item.id),
      platform_type: "self_media",
      article_count: Math.max(1, Math.min(20, Number(articleCount.value))),
      length: articleLength.value,
      style: "auto",
      content_form_codes: [...contentFormCodes.value],
      target_channel_ids: [...targetChannelIds.value],
    }),
  onMutate: () => {
    actionError.value = "";
    actionMessage.value = "";
    pendingBatchDocumentIds.value = [];
  },
  onSuccess: async (result) => {
    pendingBatchDocumentIds.value = result.items.map((document) => document.id);
    actionMessage.value = `已创建 ${result.total} 篇文章任务，AI 正在后台生成`;
    await Promise.all([
      documentsQuery.refetch(),
      generationTasksQuery.refetch(),
    ]);
  },
  onError: (error: unknown) => {
    actionError.value =
      error instanceof Error ? error.message : "批量生成文章失败";
  },
});

const openGenerationTask = async (
  task: ContentGenerationTaskData,
): Promise<void> => {
  actionError.value = "";
  selectedGenerationTask.value = task;
  generationTaskDetailLoading.value = true;
  try {
    selectedGenerationTask.value = await getContentGenerationTask(task.id);
  } catch (error) {
    actionError.value =
      error instanceof Error ? error.message : "生成任务详情载入失败";
    selectedGenerationTask.value = null;
  } finally {
    generationTaskDetailLoading.value = false;
  }
};

const confirmGenerationTaskMutation = useMutation({
  mutationFn: (task: ContentGenerationTaskData) =>
    confirmContentGenerationTask(task.id, task.version),
  onMutate: () => {
    actionError.value = "";
    actionMessage.value = "";
  },
  onSuccess: async (task) => {
    selectedGenerationTask.value = task;
    actionMessage.value = `${task.total_count} 篇文章已确认，并进入文章发布页面`;
    await Promise.all([
      generationTasksQuery.refetch(),
      documentsQuery.refetch(),
    ]);
  },
  onError: (error: unknown) => {
    actionError.value =
      error instanceof Error ? error.message : "确认生成内容失败";
  },
});

const deleteTaskDocumentMutation = useMutation({
  mutationFn: (document: ContentDocumentData) =>
    deleteDocument(document.id, document.version),
  onMutate: () => {
    actionError.value = "";
    actionMessage.value = "";
  },
  onSuccess: async (_, deletedDocument) => {
    const taskId = selectedGenerationTask.value?.id;
    deleteTaskDocumentTarget.value = null;
    if (selectedDocument.value?.id === deletedDocument.id)
      selectedDocument.value = null;
    if (taskId) {
      try {
        selectedGenerationTask.value = await getContentGenerationTask(taskId);
      } catch {
        selectedGenerationTask.value = null;
      }
    }
    await Promise.all([
      generationTasksQuery.refetch(),
      documentsQuery.refetch(),
    ]);
    actionMessage.value = `《${deletedDocument.current_version?.title ?? deletedDocument.title}》已删除`;
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof Error ? error.message : "文章删除失败";
  },
});

const generationTaskReadyForConfirmation = (
  task: ContentGenerationTaskData,
): boolean =>
  task.total_count > 0 &&
  task.status === "completed" &&
  task.failed_count === 0 &&
  task.completed_count === task.total_count &&
  (task.documents ?? []).every(canRecordPublication);

const openTaskDocument = (
  document: ContentDocumentData,
  edit = false,
): void => {
  selectedGenerationTask.value = null;
  void openDocument(document, edit);
};

const openDocument = async (
  document: ContentDocumentData,
  edit = false,
): Promise<void> => {
  actionError.value = "";
  detailLoading.value = true;
  selectedDocument.value = document;
  isEditing.value = edit;
  articleCoverStyle.value = "azure";
  articleCoverFailed.value = false;
  try {
    const detail = await getDocument(document.id);
    selectedDocument.value = detail;
    draftTitle.value = detail.current_version?.title ?? detail.title;
    draftBody.value = detail.current_version?.body_markdown ?? "";
    regenerationChannelId.value =
      detail.current_version?.target_channel_id ?? "";
    regenerationSuggestion.value = (detail.latest_check?.findings ?? [])
      .filter((finding) => finding.severity === "blocking")
      .map((finding) => finding.suggested_fix)
      .filter(Boolean)
      .map((suggestion) => suggestion.trim().replace(/[。；;]+$/, ""))
      .join("；")
      .slice(0, 2_000);
    regenerationProgress.value = "";
    regenerationCompletedMessage.value = "";
    if (edit && !detail.current_version)
      throw new Error("文章仍在生成，暂时不能编辑");
  } catch (error) {
    actionError.value =
      error instanceof Error ? error.message : "文章详情载入失败";
    if (edit) selectedDocument.value = null;
  } finally {
    detailLoading.value = false;
  }
};
const selectArticleCoverStyle = (style: ArticleCoverStyle): void => {
  articleCoverStyle.value = style;
  articleCoverFailed.value = false;
};
const beginEdit = (): void => {
  if (!selectedDocument.value?.current_version) return;
  draftTitle.value = selectedDocument.value.current_version.title;
  draftBody.value = selectedDocument.value.current_version.body_markdown;
  isEditing.value = true;
};
const selectTitleCandidate = (title: string): void => {
  draftTitle.value = title;
};
const saveMutation = useMutation({
  mutationFn: () => {
    const document = selectedDocument.value;
    if (!document?.current_version) throw new Error("文章内容尚未生成");
    return saveDocument(document.id, {
      version: document.version,
      title: draftTitle.value.trim(),
      body_markdown: draftBody.value.trim(),
      save_reason: "运营人员编辑",
    });
  },
  onMutate: () => {
    actionError.value = "";
  },
  onSuccess: async (document) => {
    selectedDocument.value = document;
    isEditing.value = false;
    actionMessage.value = "文章修改已保存";
    await documentsQuery.refetch();
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof Error ? error.message : "文章保存失败";
  },
});
const regenerateMutation = useMutation({
  mutationFn: async () => {
    const document = selectedDocument.value;
    const sourceVersion = document?.current_version;
    const instruction = regenerationSuggestion.value.trim();
    if (!document || !sourceVersion)
      throw new Error("文章正文尚未生成，不能重新生成");
    if (instruction.length < 2) throw new Error("请先填写修改建议");
    const accepted = await runDocumentOperation(
      document.id,
      crypto.randomUUID(),
      {
        operation: "regenerate",
        source_version_id: sourceVersion.id,
        revision_instruction: instruction,
        target_channel_id: regenerationChannelId.value || null,
      },
    );
    const job = await trackContentJobs(() =>
      pollJobUntilTerminal(() => getJob(accepted.job_id), {
        intervalMs: STANDARD_JOB_POLLING_INTERVAL,
        timeoutMs: 10 * 60_000,
        timeoutMessage: "AI 重新生成已等待 10 分钟仍未完成，请重新发起",
        onUpdate: (current) => {
          regenerationProgress.value = formatJobProgress(current);
        },
      }),
    );
    if (job.status !== "succeeded")
      throw new Error(job.error_message ?? "AI 重新生成失败");
    return getDocument(document.id);
  },
  onMutate: () => {
    actionError.value = "";
    actionMessage.value = "";
    regenerationProgress.value = "AI 正在根据修改建议重写完整文章…";
    regenerationCompletedMessage.value = "";
  },
  onSuccess: async (document) => {
    selectedDocument.value = document;
    draftTitle.value = document.current_version?.title ?? document.title;
    draftBody.value = document.current_version?.body_markdown ?? "";
    regenerationSuggestion.value = "";
    regenerationProgress.value = "";
    regenerationCompletedMessage.value = `已自动保存为第 ${document.current_version?.version_number ?? "最新"} 个版本，可以继续修改或直接发布。`;
    actionMessage.value = "AI 按建议重新生成完成";
    await documentsQuery.refetch();
  },
  onError: (error: unknown) => {
    regenerationProgress.value = "";
    regenerationCompletedMessage.value = "";
    actionError.value =
      error instanceof Error ? error.message : "AI 重新生成失败";
  },
});
const copyDocument = async (
  document: ContentDocumentData | null,
): Promise<void> => {
  if (!document?.current_version) {
    actionError.value = "文章仍在生成，暂时没有可复制的正文";
    return;
  }
  try {
    await navigator.clipboard.writeText(
      `${document.current_version.title}\n\n${document.current_version.body_markdown}`,
    );
    actionMessage.value = document.current_version.target_channel_id
      ? "文章标题和正文已复制"
      : "文章已复制；发布前请在编辑中选择目标平台并让 AI 重新生成";
    actionError.value = "";
  } catch {
    actionError.value = "复制失败，请打开文章后手动选择正文";
  }
};
const togglePublicationDocument = (documentId: string): void => {
  selectedPublicationDocumentIds.value =
    selectedPublicationDocumentIds.value.includes(documentId)
      ? selectedPublicationDocumentIds.value.filter(
          (item) => item !== documentId,
        )
      : [...selectedPublicationDocumentIds.value, documentId];
};
const toggleAllPublicationDocuments = (): void => {
  const visibleIds = selectablePublicationDocuments.value.map(
    (document) => document.id,
  );
  if (allVisiblePublicationDocumentsSelected.value) {
    const visible = new Set(visibleIds);
    selectedPublicationDocumentIds.value =
      selectedPublicationDocumentIds.value.filter((id) => !visible.has(id));
    return;
  }
  selectedPublicationDocumentIds.value = [
    ...new Set([...selectedPublicationDocumentIds.value, ...visibleIds]),
  ];
};
const publishDocuments = async (
  targetDocuments: ContentDocumentData[],
): Promise<void> => {
  if (!targetDocuments.length) {
    actionError.value = "请先选择需要发布的文章";
    return;
  }
  publishingDocumentIds.value = targetDocuments.map((document) => document.id);
  actionError.value = "";
  actionMessage.value = "";
  const acceptedJobs: Array<{
    job_id: string;
    account_name: string;
    document_title: string;
  }> = [];
  const failures: string[] = [];
  try {
    for (const document of targetDocuments) {
      const accounts = publishableAccountsFor(document);
      if (!accounts.length) {
        failures.push(`《${document.title}》没有可用的匹配平台账号`);
        continue;
      }
      try {
        const accepted = await publishDocument(
          document.id,
          document.version,
          accounts.map((account) => account.id),
          crypto.randomUUID(),
        );
        acceptedJobs.push(
          ...accepted.items.map((item) => ({
            job_id: item.job_id,
            account_name: item.account_name,
            document_title: document.current_version?.title ?? document.title,
          })),
        );
      } catch (error) {
        failures.push(
          `《${document.current_version?.title ?? document.title}》：${
            error instanceof Error ? error.message : "发布任务创建失败"
          }`,
        );
      }
    }
    if (!acceptedJobs.length)
      throw new Error(failures.join("；") || "没有创建发布任务");
    actionMessage.value = `${targetDocuments.length} 篇文章已进入发布队列`;
    await documentsQuery.refetch();
    const jobs = await trackContentJobs(() =>
      Promise.all(
        acceptedJobs.map((item) =>
          pollJobUntilTerminal(() => getJob(item.job_id), {
            intervalMs: PUBLISHING_JOB_POLLING_INTERVAL,
            timeoutMs: 10 * 60_000,
            timeoutMessage: `${item.account_name}发布已等待 10 分钟仍未完成，请到渠道配置检查账号状态`,
          }).then((job) => ({ ...item, job })),
        ),
      ),
    );
    const failed = jobs.filter((item) => item.job.status !== "succeeded");
    const succeeded = jobs.length - failed.length;
    await documentsQuery.refetch();
    selectedPublicationDocumentIds.value = [];
    if (failed.length || failures.length) {
      actionError.value = `成功 ${succeeded} 个，失败 ${failed.length + failures.length} 个：${[
        ...failures,
        ...failed.map(
          (item) =>
            `《${item.document_title}》/${item.account_name}（${item.job.error_message ?? "发布失败"}）`,
        ),
      ].join("；")}`;
    } else {
      actionMessage.value = `发布任务已完成，成功提交到 ${succeeded} 个平台账号`;
    }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : "文章发布失败";
    await documentsQuery.refetch();
  } finally {
    publishingDocumentIds.value = [];
  }
};
const publishSelectedDocuments = (): Promise<void> =>
  publishDocuments(selectedPublicationDocuments.value);
defineExpose({ publishSelectedDocuments });
</script>

<template>
  <p v-if="actionError" class="inline-error" role="alert">
    {{ actionError }}
  </p>
  <p v-if="actionMessage" class="inline-success" role="status">
    {{ actionMessage }}
  </p>

  <section
    v-if="
      isGenerationMode &&
      (diagnosticQuery.data.value?.is_stale || strategyOutdated)
    "
    class="stale-notice"
    role="status"
  >
    <div>
      <strong>{{
        diagnosticQuery.data.value?.is_stale
          ? "企业资料已更新"
          : "关键词策略需要更新"
      }}</strong>
      <p>
        {{
          diagnosticQuery.data.value?.is_stale
            ? "请先重新诊断并更新关键词，再生成新文章，避免使用过期信息。"
            : "当前关键词来自上一次诊断；你已明确勾选的关键词仍可继续生成，也可以先让 AI 按最新诊断更新策略。"
        }}
      </p>
    </div>
    <button
      class="button primary"
      @click="
        router.push({
          name: diagnosticQuery.data.value?.is_stale
            ? 'diagnostics'
            : 'strategy',
          query: { clientId: props.clientId },
        })
      "
    >
      {{
        diagnosticQuery.data.value?.is_stale
          ? "前往 GEO 诊断"
          : "更新关键词策略"
      }}
    </button>
  </section>

  <section v-if="isGenerationMode" class="panel content-generator">
    <div class="content-generation-flow">
      <section class="generation-step-card">
        <header>
          <b>1</b>
          <div>
            <strong>选择发布平台类型</strong>
            <p>当前版本先支持自媒体平台。</p>
          </div>
        </header>
        <div class="platform-type-options">
          <button type="button" class="platform-type-option active">
            <strong>自媒体</strong><span>已开放</span>
          </button>
          <button type="button" class="platform-type-option" disabled>
            <strong>官媒</strong><span>后续开放</span>
          </button>
          <button type="button" class="platform-type-option" disabled>
            <strong>自媒体大 V</strong><span>后续开放</span>
          </button>
        </div>
      </section>

      <section class="generation-step-card">
        <header>
          <b>2</b>
          <div>
            <strong>选择关键词</strong>
            <p>从已经确认保存的正式关键词中选择，最多 20 个。</p>
          </div>
          <div class="keyword-step-actions">
            <span class="step-selection-count"
              >已选 {{ selectedKeywords.length }}</span
            >
            <button
              type="button"
              class="keyword-select-all"
              :disabled="!officialKeywords.length"
              @click="toggleAllKeywords"
            >
              {{ areAllKeywordsSelected ? "取消全选" : "全选" }}
            </button>
          </div>
        </header>
        <div v-if="officialKeywords.length" class="keyword-choice-list">
          <label
            v-for="item in officialKeywords"
            :key="item.id"
            :class="{ selected: selectedKeywordIds.includes(item.id) }"
          >
            <input
              v-model="selectedKeywordIds"
              type="checkbox"
              :value="item.id"
              :disabled="
                selectedKeywordIds.length >= 20 &&
                !selectedKeywordIds.includes(item.id)
              "
            />
            <span>
              <strong>{{ item.text }}</strong>
              <small>{{
                keywordTypeLabel[item.keyword_type ?? ""] ?? "综合关键词"
              }}</small>
            </span>
          </label>
        </div>
        <div v-else class="content-keyword-empty">
          <strong>没有可选的正式关键词</strong>
          <p>请先到关键词页面生成并确认保存关键词。</p>
        </div>
      </section>

      <section class="generation-step-card">
        <header>
          <b>3</b>
          <div>
            <strong>选择自媒体平台</strong>
            <p>只有已连接并启用账号的平台可以选择。</p>
          </div>
          <span class="step-selection-count">{{ selectedChannelSummary }}</span>
        </header>
        <div class="generation-channel-grid">
          <label
            v-for="channel in targetChannels"
            :key="channel.id"
            :class="{
              selected: targetChannelIds.includes(channel.id),
              unavailable: !channel.selectable,
            }"
          >
            <input
              v-model="targetChannelIds"
              type="checkbox"
              :value="channel.id"
              :disabled="!channel.selectable"
            />
            <span>
              <strong>{{ channel.name }}</strong>
              <small>{{
                channel.selectable
                  ? `${channel.enabled_count} 个可用账号`
                  : channel.unavailable_reason
              }}</small>
            </span>
          </label>
        </div>
        <button
          v-if="targetChannels.some((channel) => !channel.selectable)"
          type="button"
          class="text-action"
          @click="
            router.push({
              name: 'channels',
              query: { clientId: props.clientId },
            })
          "
        >
          前往渠道配置
        </button>
      </section>

      <section class="generation-step-card">
        <header>
          <b>4</b>
          <div>
            <strong>设置文章规格</strong>
            <p>篇数按每个平台计算，内容形式会在每个平台内均衡分配。</p>
          </div>
        </header>
        <div class="generation-config generation-config--compact">
          <label class="field compact-field">
            <span>每个平台篇数</span>
            <input
              v-model.number="articleCount"
              type="number"
              min="1"
              max="20"
            />
          </label>
          <label class="field compact-field">
            <span>文章长度</span>
            <select v-model="articleLength">
              <option value="short">短篇（约 600—900 字）</option>
              <option value="medium">中篇（约 1000—1500 字）</option>
              <option value="long">长篇（约 1600—2200 字）</option>
            </select>
          </label>
        </div>
        <div class="content-form-picker">
          <span>内容形式（可多选）</span>
          <div>
            <label
              v-for="template in contentFormTemplates"
              :key="template.id"
              :class="{ selected: isContentFormSelected(template.code) }"
            >
              <input
                type="checkbox"
                :checked="isContentFormSelected(template.code)"
                @change="toggleContentForm(template.code)"
              />
              <span
                ><strong>{{ template.name }}</strong
                ><small>{{ template.description }}</small></span
              >
            </label>
          </div>
        </div>
      </section>
    </div>
    <div class="generation-submit-bar">
      <div>
        <strong>预计生成 {{ plannedArticleCount }} 篇</strong>
        <span
          >{{ targetChannelIds.length }} 个平台 × 每个平台
          {{ articleCount }} 篇</span
        >
      </div>
      <button
        class="button primary generate-content-button"
        :disabled="!canGenerate"
        @click="batchMutation.mutate()"
      >
        {{ batchMutation.isPending.value ? "正在创建任务…" : "开始 AI 生成" }}
      </button>
    </div>
    <p
      v-if="
        !canGenerate &&
        (generationLimitError ||
          generationConfigurationError ||
          generationAvailability.reason)
      "
      class="generation-disabled-reason"
      role="status"
    >
      {{
        generationLimitError ||
        generationConfigurationError ||
        generationAvailability.reason
      }}
    </p>
    <div class="generation-guidance generation-guidance--simple">
      <div>
        <strong>生成时自动完成质量与平台规则检查</strong>
        <span>
          AI
          会以企业知识库为事实边界，优先写专业方法和真实信息，控制营销表达、品牌次数与关键词密度，并按所选平台自动处理联系方式和外链。可修复问题会在后台自动重写，只有无法安全处理的问题才标记为“需调整”。
        </span>
      </div>
    </div>
    <p class="generation-note">
      生成任务提交后可离开页面；后台完成时会自动通知，无需手动刷新。
    </p>
  </section>

  <section v-if="isGenerationMode" class="panel generation-task-panel">
    <header class="panel-header">
      <div>
        <h2>文章生成任务</h2>
        <p>每次生成都会保留配置与进度；点击查看可进入本次文章列表。</p>
      </div>
      <span
        v-if="
          generationTasks.some((task) =>
            ['queued', 'generating'].includes(task.status),
          )
        "
        class="generation-live"
      >
        <span class="task-pulse" />后台正在生成
      </span>
    </header>
    <div v-if="generationTasksQuery.isPending.value" class="empty-inline">
      <p>正在载入生成任务…</p>
    </div>
    <div
      v-else-if="generationTasksQuery.isError.value"
      class="empty-inline error-state"
    >
      <strong>生成任务暂时无法载入</strong>
      <button
        class="button secondary"
        type="button"
        @click="generationTasksQuery.refetch()"
      >
        重新加载
      </button>
    </div>
    <div v-else class="table-scroll">
      <table class="data-table generation-task-table">
        <thead>
          <tr>
            <th>关键词</th>
            <th>发布平台类型</th>
            <th>自媒体平台</th>
            <th>文章总数</th>
            <th>生成状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in generationTasks" :key="task.id">
            <td>
              <span
                class="task-keyword-summary"
                :title="taskKeywordSummary(task)"
              >
                {{ taskKeywordSummary(task) }}
              </span>
            </td>
            <td><span class="soft-badge">自媒体</span></td>
            <td>{{ taskChannelSummary(task) }}</td>
            <td>
              <strong>{{ task.total_count }}</strong>
              <small class="table-subtext"
                >每个平台 {{ task.article_count_per_channel }} 篇</small
              >
            </td>
            <td>
              <span class="task-status-pill" :data-status="task.status">
                {{
                  task.confirmed_at
                    ? "已确认"
                    : generationTaskStatusLabel[task.status]
                }}
              </span>
              <small
                v-if="['queued', 'generating'].includes(task.status)"
                class="table-subtext"
              >
                {{ task.progress }}%
              </small>
              <small
                v-else-if="task.failed_count"
                class="table-subtext error-text"
              >
                失败 {{ task.failed_count }} 篇
              </small>
            </td>
            <td>{{ formatDateTime(task.created_at) }}</td>
            <td>
              <button
                class="text-action primary"
                type="button"
                @click="openGenerationTask(task)"
              >
                查看
              </button>
            </td>
          </tr>
          <tr v-if="generationTasks.length === 0">
            <td colspan="7" class="table-empty">
              暂无生成任务，请先完成上方配置并开始生成。
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section v-if="isPublishingMode" class="panel article-list-panel">
    <header class="panel-header">
      <div>
        <h2>文章发布</h2>
        <p>这里只展示已在内容工作台确认、可以直接提交平台的文章。</p>
      </div>
      <div class="article-list-toolbar">
        <nav class="filter-tabs" aria-label="文章列表分类">
          <button
            class="button"
            :class="{
              primary: publicationView === 'unpublished',
              secondary: publicationView !== 'unpublished',
            }"
            type="button"
            @click="publicationView = 'unpublished'"
          >
            未发布 {{ publicationCounts.unpublished }}
          </button>
          <button
            class="button"
            :class="{
              primary: publicationView === 'published',
              secondary: publicationView !== 'published',
            }"
            type="button"
            @click="publicationView = 'published'"
          >
            已发布 {{ publicationCounts.published }}
          </button>
          <button
            class="button"
            :class="{
              primary: publicationView === 'failed',
              secondary: publicationView !== 'failed',
            }"
            type="button"
            @click="publicationView = 'failed'"
          >
            发布失败 {{ publicationCounts.failed }}
          </button>
        </nav>
      </div>
    </header>
    <div class="article-filter-panel" aria-label="文章筛选">
      <label class="search-field">
        <span class="sr-only">按关键词或标题筛选</span>
        <input
          v-model="articleKeywordFilter"
          placeholder="搜索关键词或文章标题"
        />
      </label>
      <label class="select-field">
        <span class="sr-only">关键词类型</span>
        <select v-model="articleTypeFilter">
          <option value="all">全部类型</option>
          <option
            v-for="(label, value) in keywordTypeLabel"
            :key="value"
            :value="value"
          >
            {{ label }}
          </option>
        </select>
      </label>
      <label class="select-field">
        <span class="sr-only">发布平台</span>
        <select v-model="articleChannelFilter">
          <option value="all">全部发布平台</option>
          <option
            v-for="channel in targetChannels"
            :key="channel.id"
            :value="channel.id"
          >
            {{ channel.name }}
          </option>
        </select>
      </label>
      <span class="article-filter-count">
        {{ filteredDocuments.length }} / {{ visibleDocuments.length }} 篇
      </span>
    </div>
    <div
      v-if="visibleDocumentsPending"
      class="loading-panel compact-loading"
      aria-busy="true"
    >
      <span class="loading-orbit" />
      <p>正在载入文章列表…</p>
    </div>
    <div v-else-if="visibleDocumentsError" class="empty-inline">
      <strong>文章列表暂时无法载入</strong>
      <button class="button secondary" @click="documentsQuery.refetch()">
        重新载入
      </button>
    </div>
    <div v-else class="data-table-wrap">
      <table class="data-table article-table">
        <caption class="sr-only">
          AI 生成文章列表
        </caption>
        <thead>
          <tr>
            <th v-if="publicationView !== 'published'" class="selection-cell">
              <input
                type="checkbox"
                aria-label="全选当前可发布文章"
                :checked="allVisiblePublicationDocumentsSelected"
                :disabled="selectablePublicationDocuments.length === 0"
                @change="toggleAllPublicationDocuments"
              />
            </th>
            <th>文章标题</th>
            <th>对应关键词</th>
            <th>发布平台</th>
            <th>发布状态</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="document in filteredDocuments" :key="document.id">
            <td v-if="publicationView !== 'published'" class="selection-cell">
              <input
                type="checkbox"
                :aria-label="`选择文章：${document.current_version?.title ?? document.title}`"
                :checked="selectedPublicationDocumentIds.includes(document.id)"
                :disabled="!canOneClickPublish(document)"
                @change="togglePublicationDocument(document.id)"
              />
            </td>
            <td class="article-title-cell">
              <button class="article-title" @click="openDocument(document)">
                {{ document.current_version?.title ?? document.title }}
              </button>
            </td>
            <td class="article-keyword-cell">
              <span
                class="article-keyword-chip"
                :title="document.keyword ?? undefined"
              >
                <span class="article-keyword-dot" aria-hidden="true" />
                <span class="article-keyword-text">
                  {{ document.keyword ?? "—" }}
                </span>
              </span>
            </td>
            <td>
              <div class="article-channel-list">
                <span
                  v-for="name in suitableChannelNames(document)"
                  :key="name"
                >
                  {{ name }}
                </span>
                <small v-if="suitableChannelNames(document).length === 0">
                  暂未指定
                </small>
              </div>
            </td>
            <td>
              <span
                :class="`content-status publication-status publication-status--${publicationStatusTone(document)}`"
              >
                {{ publicationStatusText(document) }}
              </span>
              <small
                v-if="document.publication_error"
                class="publication-error"
                :title="document.publication_error"
              >
                {{ document.publication_error }}
              </small>
              <small
                v-if="document.publication_status === 'pending_review'"
                class="publication-review-note"
              >
                已提交平台，系统约每 10 分钟自动复查
              </small>
              <a
                v-if="document.latest_publication?.public_url"
                class="publication-link"
                :href="document.latest_publication.public_url"
                target="_blank"
                rel="noopener noreferrer"
              >
                查看原文
              </a>
            </td>
            <td>{{ formatDateTime(document.updated_at) }}</td>
            <td>
              <div class="table-actions">
                <button class="text-action" @click="openDocument(document)">
                  查看
                </button>
                <button
                  v-if="publicationView !== 'published'"
                  class="text-action primary"
                  :disabled="
                    !canOneClickPublish(document) ||
                    publishingDocumentIds.includes(document.id)
                  "
                  :title="
                    canOneClickPublish(document)
                      ? '按文章指定平台发布到全部已连接账号'
                      : ['queued', 'publishing', 'pending_review'].includes(
                            document.publication_status,
                          )
                        ? '发布任务正在处理中'
                        : '匹配平台暂无可用账号'
                  "
                  @click="publishDocuments([document])"
                >
                  {{
                    document.publication_status === "queued"
                      ? "等待发布"
                      : document.publication_status === "publishing"
                        ? "发布中…"
                        : document.publication_status === "pending_review"
                          ? "平台审核中"
                          : publicationView === "failed"
                            ? "重新发布"
                            : "发布"
                  }}
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="filteredDocuments.length === 0">
            <td
              :colspan="publicationView === 'published' ? 6 : 7"
              class="table-empty"
            >
              {{
                visibleDocuments.length > 0
                  ? "没有符合当前筛选条件的文章。"
                  : publicationView === "published"
                    ? "暂无已发布文章。"
                    : publicationView === "failed"
                      ? "暂无发布失败文章。"
                      : "暂无待发布文章。请先在内容工作台确认已完成的生成任务。"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="article-publish-note">
      发布会自动使用文章指定平台下所有已连接且已启用的账号；平台审核结果会由系统自动更新。
    </p>
  </section>

  <ModalDialog
    v-if="selectedGenerationTask"
    title="本次生成的文章"
    size="large"
    @close="selectedGenerationTask = null"
  >
    <section class="generation-task-detail">
      <div class="generation-task-snapshot">
        <div>
          <span>关键词</span
          ><strong :title="taskKeywordSummary(selectedGenerationTask)">{{
            taskKeywordSummary(selectedGenerationTask)
          }}</strong>
        </div>
        <div>
          <span>自媒体平台</span
          ><strong>{{ taskChannelSummary(selectedGenerationTask) }}</strong>
        </div>
        <div>
          <span>内容形式</span
          ><strong>{{ taskContentFormSummary(selectedGenerationTask) }}</strong>
        </div>
        <div>
          <span>文章数量</span
          ><strong>{{ selectedGenerationTask.total_count }} 篇</strong>
        </div>
      </div>
      <div v-if="generationTaskDetailLoading" class="empty-inline">
        <p>正在载入本次文章…</p>
      </div>
      <div v-else class="table-scroll">
        <table class="data-table task-document-table">
          <thead>
            <tr>
              <th>文章标题</th>
              <th>对应关键词</th>
              <th>平台</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="document in selectedGenerationTask.documents ?? []"
              :key="document.id"
            >
              <td>
                <strong>{{
                  document.current_version?.title ?? document.title
                }}</strong>
              </td>
              <td>{{ document.keyword ?? "综合内容" }}</td>
              <td>
                {{
                  channelName(
                    document.current_version?.target_channel_id ??
                      document.fact_snapshot?.brief_context.target_channel_id,
                  )
                }}
              </td>
              <td>
                <span
                  class="content-status"
                  :data-tone="contentStatusTone(document)"
                  >{{ contentStatusLabel(document) }}</span
                >
              </td>
              <td>
                <div class="row-actions">
                  <button
                    class="text-action"
                    type="button"
                    @click="openTaskDocument(document)"
                  >
                    查看
                  </button>
                  <button
                    class="text-action primary"
                    type="button"
                    :disabled="!document.current_version"
                    @click="openTaskDocument(document, true)"
                  >
                    编辑
                  </button>
                  <button
                    class="text-action danger"
                    type="button"
                    :disabled="
                      ['pending', 'generating'].includes(
                        document.generation_status,
                      )
                    "
                    :title="
                      ['pending', 'generating'].includes(
                        document.generation_status,
                      )
                        ? '文章生成完成后才可删除'
                        : '删除这篇文章'
                    "
                    @click="deleteTaskDocumentTarget = document"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="(selectedGenerationTask.documents ?? []).length === 0">
              <td colspan="5" class="table-empty">
                {{
                  selectedGenerationTask.total_count === 0
                    ? "本次生成的文章已全部删除。"
                    : "文章任务正在初始化，请稍后再次查看。"
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="generation-task-confirmation">
        <div
          v-if="selectedGenerationTask.confirmed_at"
          class="confirmation-ready"
        >
          <strong>已确认进入文章发布</strong>
          <span>这些文章已经出现在“文章发布”的未发布列表中。</span>
        </div>
        <template v-else>
          <div>
            <strong>确认本次生成内容</strong>
            <span>
              确认后，本次全部合格文章将进入文章发布页面，可直接单篇或批量发布。
            </span>
          </div>
          <button
            class="button primary"
            type="button"
            :disabled="
              !generationTaskReadyForConfirmation(selectedGenerationTask) ||
              confirmGenerationTaskMutation.isPending.value
            "
            :title="
              generationTaskReadyForConfirmation(selectedGenerationTask)
                ? '确认后进入文章发布页面'
                : '请等待全部文章生成完成并达到可发布标准'
            "
            @click="
              confirmGenerationTaskMutation.mutate(selectedGenerationTask)
            "
          >
            {{
              confirmGenerationTaskMutation.isPending.value
                ? "正在确认…"
                : "确认内容，进入发布"
            }}
          </button>
        </template>
      </footer>
    </section>
  </ModalDialog>

  <ModalDialog
    v-if="deleteTaskDocumentTarget"
    title="删除文章"
    size="small"
    :close-disabled="deleteTaskDocumentMutation.isPending.value"
    @close="deleteTaskDocumentTarget = null"
  >
    <div class="confirm-dialog-copy">
      <p>
        确定删除“{{
          deleteTaskDocumentTarget.current_version?.title ??
          deleteTaskDocumentTarget.title
        }}”吗？
      </p>
      <small
        >删除后，这篇文章不会进入文章发布页面；本次任务的文章数量会同步更新。</small
      >
    </div>
    <footer class="modal-actions">
      <button
        class="button secondary"
        type="button"
        :disabled="deleteTaskDocumentMutation.isPending.value"
        @click="deleteTaskDocumentTarget = null"
      >
        取消
      </button>
      <button
        class="button danger"
        type="button"
        :disabled="deleteTaskDocumentMutation.isPending.value"
        @click="deleteTaskDocumentMutation.mutate(deleteTaskDocumentTarget)"
      >
        {{
          deleteTaskDocumentMutation.isPending.value ? "正在删除…" : "确认删除"
        }}
      </button>
    </footer>
  </ModalDialog>

  <ModalDialog
    v-if="selectedDocument"
    :title="isEditing ? '编辑文章' : '文章详情'"
    size="large"
    :close-disabled="
      saveMutation.isPending.value || regenerateMutation.isPending.value
    "
    @close="selectedDocument = null"
  >
    <div v-if="detailLoading" class="loading-panel compact-loading">
      <span class="loading-orbit" />
      <p>正在载入文章正文…</p>
    </div>
    <form
      v-else-if="isEditing"
      class="article-editor"
      @submit.prevent="saveMutation.mutate()"
    >
      <section
        v-if="blockingFindingCount(selectedDocument)"
        class="quality-correction-panel"
      >
        <header>
          <div>
            <strong>这篇文章需要调整</strong>
            <p>
              生成时已经自动执行平台规则和质量修复。以下问题无法安全自动修改，请手工确认，或让
              AI 按建议重新生成。
            </p>
          </div>
          <span>{{ blockingFindingCount(selectedDocument) }} 项需处理</span>
        </header>
        <ul>
          <li
            v-for="finding in blockingFindings(selectedDocument)"
            :key="finding.id"
            :data-severity="finding.severity"
          >
            <span>{{
              qualityCategoryLabel[finding.category] ?? finding.category
            }}</span>
            <div>
              <strong>{{ finding.message }}</strong>
              <p>{{ finding.suggested_fix }}</p>
            </div>
          </li>
        </ul>
      </section>
      <section
        v-if="selectedDocument.current_version?.title_candidates?.length"
        class="title-candidate-panel"
      >
        <header>
          <div>
            <strong>AI 候选标题</strong>
            <p>
              标题先服务读者。选择后仍可在下方继续修改，保存时与正文一起形成新版本。
            </p>
          </div>
          <span
            >{{
              selectedDocument.current_version.title_candidates.length
            }}
            个方向</span
          >
        </header>
        <div class="title-candidate-list">
          <button
            v-for="candidate in selectedDocument.current_version
              .title_candidates"
            :key="`${candidate.title_type}-${candidate.title}`"
            type="button"
            :class="{ active: draftTitle === candidate.title }"
            :aria-pressed="draftTitle === candidate.title"
            @click="selectTitleCandidate(candidate.title)"
          >
            <span>{{
              titleCandidateTypeLabel[candidate.title_type] ?? "候选标题"
            }}</span>
            <strong>{{ candidate.title }}</strong>
            <small>{{
              draftTitle === candidate.title ? "当前使用" : "点击采用"
            }}</small>
          </button>
        </div>
      </section>
      <label class="field">
        <span>文章标题</span>
        <input v-model="draftTitle" required />
      </label>
      <label class="field article-body-field">
        <span>文章正文</span>
        <textarea v-model="draftBody" rows="20" required />
      </label>
      <section class="ai-regeneration-panel">
        <div class="ai-regeneration-heading">
          <div>
            <strong>让 AI 重新生成</strong>
            <p>
              填写你想怎么改，AI 会继续使用企业资料{{
                selectedDocument.current_version?.target_channel_id
                  ? `和${channelName(selectedDocument.current_version.target_channel_id)}平台`
                  : "和通用内容"
              }}规则生成完整新版本。
            </p>
          </div>
          <span>完成后自动保存</span>
        </div>
        <label class="field">
          <span>修改建议</span>
          <textarea
            v-model="regenerationSuggestion"
            rows="4"
            maxlength="2000"
            placeholder="例如：删除推广语，减少品牌出现次数，改成搜狐号可发布的客观选择指南，不要出现联系方式"
          />
        </label>
        <label
          v-if="!selectedDocument.current_version?.target_channel_id"
          class="field"
        >
          <span>发布平台</span>
          <select v-model="regenerationChannelId">
            <option value="">暂不指定平台</option>
            <option
              v-for="channel in targetChannels"
              :key="channel.id"
              :value="channel.id"
            >
              {{ channel.name }}
            </option>
          </select>
        </label>
        <p v-if="regenerationProgress" class="task-banner">
          <span class="task-pulse" />{{ regenerationProgress }}
        </p>
        <div
          v-if="regenerationCompletedMessage"
          class="regeneration-complete"
          role="status"
        >
          <strong>AI 重新生成完成</strong>
          <span>{{ regenerationCompletedMessage }}</span>
        </div>
        <button
          class="button ai-regenerate-button"
          type="button"
          :disabled="
            regenerateMutation.isPending.value ||
            regenerationSuggestion.trim().length < 2
          "
          @click="regenerateMutation.mutate()"
        >
          {{
            regenerateMutation.isPending.value
              ? "AI 正在重新生成…"
              : "AI 按建议重新生成"
          }}
        </button>
      </section>
      <footer class="modal-actions">
        <button
          class="button secondary"
          type="button"
          :disabled="
            saveMutation.isPending.value || regenerateMutation.isPending.value
          "
          @click="isEditing = false"
        >
          取消编辑
        </button>
        <button
          class="button primary"
          type="submit"
          :disabled="
            saveMutation.isPending.value || regenerateMutation.isPending.value
          "
        >
          {{ saveMutation.isPending.value ? "保存中…" : "保存修改" }}
        </button>
      </footer>
    </form>
    <article v-else class="article-detail">
      <header>
        <span class="keyword-type">
          {{ selectedDocument.keyword ?? "综合内容" }}
        </span>
        <h2>
          {{
            selectedDocument.current_version?.title ?? selectedDocument.title
          }}
        </h2>
        <div
          v-if="selectedDocument.current_version"
          class="article-generation-meta"
        >
          <span>
            内容形式
            <strong>{{
              contentFormName(
                selectedDocument.current_version.prompt_template_code,
              )
            }}</strong>
          </span>
          <span>
            发布平台
            <strong>{{
              channelName(selectedDocument.current_version.target_channel_id)
            }}</strong>
          </span>
        </div>
        <section
          v-if="
            selectedDocument.current_version &&
            !selectedDocument.current_version.target_channel_id
          "
          class="channel-adaptation-warning"
        >
          这篇文章尚未指定发布平台。发布前请进入编辑，选择平台后让 AI
          重新生成，系统会自动应用该平台的标题、营销、联系方式和外链规则。
        </section>
        <section
          v-if="
            selectedDocument.current_version?.contact_sanitization_report
              ?.changed
          "
          class="sanitization-summary"
        >
          生成时已按平台规则自动清理：
          {{
            selectedDocument.current_version.contact_sanitization_report
              .removed_phone_or_wechat ?? 0
          }}
          类联系方式、
          {{
            selectedDocument.current_version.contact_sanitization_report
              .removed_qr_or_guidance ?? 0
          }}
          类二维码/导流表达、
          {{
            selectedDocument.current_version.contact_sanitization_report
              .removed_urls ?? 0
          }}
          个链接。
        </section>
        <section
          v-if="blockingFindingCount(selectedDocument)"
          class="quality-correction-panel quality-correction-panel--detail"
        >
          <header>
            <div>
              <strong>这篇文章需要调整</strong>
              <p>打开编辑可查看具体原因，并让 AI 按建议重新生成。</p>
            </div>
            <span> {{ blockingFindingCount(selectedDocument) }} 项需处理 </span>
          </header>
        </section>
      </header>
      <section
        v-if="selectedDocument.current_version?.image_material_ids.length"
        class="article-inline-images"
      >
        <div class="article-cover-heading">
          <div>
            <span>正文配图</span>
            <strong>
              已从企业图片库选中
              {{ selectedDocument.current_version.image_material_ids.length }}
              张
            </strong>
          </div>
          <small>一键发布时会自动插入正文段落之间</small>
        </div>
        <div class="article-inline-image-grid">
          <img
            v-for="materialId in selectedDocument.current_version
              .image_material_ids"
            :key="materialId"
            :src="materialFileUrl(materialId)"
            alt="企业正文配图"
            loading="lazy"
          />
        </div>
      </section>
      <section
        v-if="selectedDocument.current_version"
        class="article-cover-workbench"
      >
        <div class="article-cover-heading">
          <div>
            <span>文章封面</span>
            <strong>已按本篇标题自动生成</strong>
          </div>
          <small>1200 × 675 PNG · 不额外消耗模型额度</small>
        </div>
        <div class="article-cover-layout">
          <div class="article-cover-preview" :data-style="articleCoverStyle">
            <img
              v-if="!articleCoverFailed"
              :src="
                articleCoverUrl(
                  selectedDocument.id,
                  selectedDocument.current_version.id,
                  articleCoverStyle,
                  false,
                  selectedDocument.current_version.image_material_ids,
                )
              "
              :alt="`${selectedDocument.current_version.title}文章封面`"
              @error="articleCoverFailed = true"
            />
            <div v-else class="article-cover-error" role="status">
              <strong>封面暂时无法生成</strong>
              <span>请稍后重新打开文章详情。</span>
            </div>
          </div>
          <div class="article-cover-controls">
            <div class="article-cover-style-list" aria-label="选择封面风格">
              <button
                v-for="style in ARTICLE_COVER_STYLES"
                :key="style.value"
                type="button"
                :class="{ active: articleCoverStyle === style.value }"
                :aria-pressed="articleCoverStyle === style.value"
                @click="selectArticleCoverStyle(style.value)"
              >
                <span :data-color="style.value" aria-hidden="true" />
                <div>
                  <strong>{{ style.label }}</strong>
                  <small>{{ style.description }}</small>
                </div>
              </button>
            </div>
            <a
              class="button primary article-cover-download"
              :href="
                articleCoverUrl(
                  selectedDocument.id,
                  selectedDocument.current_version.id,
                  articleCoverStyle,
                  true,
                  selectedDocument.current_version.image_material_ids,
                )
              "
            >
              下载封面 PNG
            </a>
          </div>
        </div>
      </section>
      <div v-if="selectedDocument.current_version" class="article-body">
        {{ selectedDocument.current_version.body_markdown }}
      </div>
      <div v-else class="empty-inline">
        <strong>正文正在生成</strong>
        <p>稍后重新打开即可查看完整内容。</p>
      </div>
      <footer class="modal-actions">
        <button
          class="button secondary"
          :disabled="!selectedDocument.current_version"
          @click="copyDocument(selectedDocument)"
        >
          复制全文
        </button>
        <button
          class="button primary"
          :disabled="!selectedDocument.current_version"
          @click="beginEdit"
        >
          {{
            blockingFindingCount(selectedDocument)
              ? "查看问题并修正"
              : "编辑文章"
          }}
        </button>
      </footer>
    </article>
  </ModalDialog>
</template>
