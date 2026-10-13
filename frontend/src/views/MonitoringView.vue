<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getClient } from "../api/clients";
import type {
  MonitoringEvaluationData,
  MonitoringSampleData,
} from "../api/dto";
import {
  createMonitoringFeedback,
  createMonitoringBatch,
  createQuestionSet,
  getLatestMonitoringBatch,
  getMonitoringMetrics,
  getOptimizationActions,
  getPlatforms,
  getQuestionSets,
  saveManualSamples,
  updateMonitoringEvaluation,
} from "../api/monitoring";
import {
  pollJobUntilTerminal,
  createStagedPollingInterval,
} from "../api/jobPolling";
import { getJob, getStrategy } from "../api/strategy";
import AppShell from "../components/AppShell.vue";
import {
  BASELINE_QUESTION_LIMIT,
  selectedKeywordMonitoringQuestions,
} from "../monitoringQuestionLogic";
import { useWorkspaceStore } from "../stores/workspace";
import {
  notifyRequestError,
  notifyRequestInfo,
  notifyRequestSuccess,
} from "../requestNotifications";

const route = useRoute();
const workspace = useWorkspaceStore();
const queryClient = useQueryClient();
const sampleFilter = ref<"all" | "attention" | "manual">("all");
const metricMode = ref<"api" | "manual_consumer">("api");
const selectedSampleId = ref("");
const manualAnswer = ref("");
const manualFailed = ref(false);
const manualFailureReason = ref("");
const createdActionId = ref("");
const selectedPlatformIds = ref<string[]>([]);
const platformSelectionInitialized = ref(false);
const formatDateKey = (value: Date): string => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};
const metricsTo = formatDateKey(new Date());
const metricsStart = new Date();
metricsStart.setDate(metricsStart.getDate() - 29);
const metricsFrom = formatDateKey(metricsStart);
const reviewState = ref({
  brand_found: false,
  correctly_associated: false,
  recommended: false,
  recommendation_supported: null as boolean | null,
  facts_accurate: null as boolean | null,
  note: "",
});

const clientId = computed(() =>
  typeof route.query.clientId === "string"
    ? route.query.clientId
    : workspace.currentClientId,
);
const clientQuery = useQuery({
  queryKey: computed(() => ["client", clientId.value]),
  queryFn: () => getClient(clientId.value),
  enabled: computed(() => Boolean(clientId.value)),
});
const platformsQuery = useQuery({
  queryKey: ["monitoring-platforms"],
  queryFn: getPlatforms,
});
watch(
  () => platformsQuery.data.value?.items,
  (platforms) => {
    if (!platforms || platformSelectionInitialized.value) return;
    selectedPlatformIds.value = platforms
      .filter((platform) => platform.active)
      .map((platform) => platform.id);
    platformSelectionInitialized.value = true;
  },
  { immediate: true },
);
const selectedPlatformCount = computed(
  () =>
    (platformsQuery.data.value?.items ?? []).filter(
      (platform) =>
        platform.active && selectedPlatformIds.value.includes(platform.id),
    ).length,
);
const selectPlatformScope = (scope: "all" | "P0"): void => {
  selectedPlatformIds.value = (platformsQuery.data.value?.items ?? [])
    .filter(
      (platform) =>
        platform.active && (scope === "all" || platform.priority === scope),
    )
    .map((platform) => platform.id);
  platformSelectionInitialized.value = true;
};
const togglePlatform = (platformId: string): void => {
  selectedPlatformIds.value = selectedPlatformIds.value.includes(platformId)
    ? selectedPlatformIds.value.filter((item) => item !== platformId)
    : [...selectedPlatformIds.value, platformId];
  platformSelectionInitialized.value = true;
};
const questionSetsQuery = useQuery({
  queryKey: computed(() => ["monitoring-question-sets", clientId.value]),
  queryFn: () => getQuestionSets(clientId.value),
  enabled: computed(() => Boolean(clientId.value)),
});
const strategyQuery = useQuery({
  queryKey: computed(() => ["strategy", clientId.value]),
  queryFn: () => getStrategy(clientId.value),
  enabled: computed(() => Boolean(clientId.value)),
});
const frozenQuestionSet = computed(() =>
  questionSetsQuery.data.value?.items.find((item) => item.frozen),
);
const selectedKeywordCount = computed(
  () =>
    (strategyQuery.data.value?.items ?? []).filter(
      (item) => item.kind === "keyword" && item.active && item.selected,
    ).length,
);
const baselineQuestions = computed(() =>
  selectedKeywordMonitoringQuestions(strategyQuery.data.value?.items ?? []),
);
const monitoringReady = computed(
  () => Boolean(frozenQuestionSet.value) || baselineQuestions.value.length > 0,
);
const batchQuery = useQuery({
  queryKey: computed(() => ["monitoring", clientId.value]),
  queryFn: () => getLatestMonitoringBatch(clientId.value),
  enabled: computed(() => Boolean(clientId.value)),
});
const metricsQuery = useQuery({
  queryKey: computed(() => [
    "monitoring-metrics",
    clientId.value,
    metricsFrom,
    metricsTo,
  ]),
  queryFn: () => getMonitoringMetrics(clientId.value, metricsFrom, metricsTo),
  enabled: computed(() => Boolean(clientId.value)),
});
const actionsQuery = useQuery({
  queryKey: computed(() => ["optimization-actions", clientId.value]),
  queryFn: () => getOptimizationActions(clientId.value),
  enabled: computed(() => Boolean(clientId.value)),
});

const waitForJob = async (jobId: string): Promise<void> => {
  const job = await pollJobUntilTerminal(() => getJob(jobId), {
    intervalMs: createStagedPollingInterval([
      { untilMs: 60_000, intervalMs: 5_000 },
      { untilMs: 5 * 60_000, intervalMs: 10_000 },
      { intervalMs: 15_000 },
    ]),
    timeoutMs: 15 * 60_000,
    timeoutMessage: "AI 平台监测已等待 15 分钟仍未完成，请重新发起监测",
  });
  if (job.status === "succeeded") return;
  throw new Error(job.error_message || "监测任务执行失败");
};

const startMutation = useMutation({
  mutationFn: async () => {
    if (!clientId.value) throw new Error("请先选择客户");
    const [clientResult, questionSetsResult, strategyResult, platformsResult] =
      await Promise.all([
        clientQuery.refetch(),
        questionSetsQuery.refetch(),
        strategyQuery.refetch(),
        platformsQuery.refetch(),
      ]);
    const customer = clientResult.data;
    if (!customer) throw new Error("客户资料暂时不可用，请刷新后重试");
    let questionSet = questionSetsResult.data?.items.find(
      (item) => item.frozen,
    );
    if (!questionSet) {
      const monitoringQuestions = selectedKeywordMonitoringQuestions(
        strategyResult.data?.items ?? [],
      );
      if (!monitoringQuestions.length)
        throw new Error(
          "请先到“关键词”页面生成关键词，并勾选至少一个用于监测的问题。",
        );
      questionSet = await createQuestionSet(clientId.value, {
        name: `${customer.district || customer.city}${customer.industry_name}监测基线`,
        frozen: true,
        questions: monitoringQuestions,
      });
    }
    const activePlatformIds = (platformsResult.data?.items ?? [])
      .filter((item) => item.active)
      .map((item) => item.id);
    const platformIds = (
      platformSelectionInitialized.value
        ? selectedPlatformIds.value
        : activePlatformIds
    ).filter((platformId) => activePlatformIds.includes(platformId));
    if (!platformIds.length) throw new Error("请至少选择一个监测平台");
    const result = await createMonitoringBatch(
      clientId.value,
      {
        question_set_id: questionSet.id,
        platform_ids: platformIds,
        api_sample_count: batchQuery.data.value ? 3 : 1,
        manual_placeholders: true,
      },
      crypto.randomUUID(),
    );
    await waitForJob(result.job.id);
  },
  onMutate: () => {
    notifyRequestInfo("AI 平台监测已开始", "采样完成后会自动更新结果");
  },
  onSuccess: async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["monitoring", clientId.value],
      }),
      queryClient.invalidateQueries({
        queryKey: ["monitoring-question-sets", clientId.value],
      }),
      queryClient.invalidateQueries({
        queryKey: ["monitoring-metrics", clientId.value],
      }),
    ]);
    notifyRequestSuccess("AI 平台监测完成", "最新监测结果与指标已更新");
  },
  onError: (error: unknown) => {
    notifyRequestError(
      "AI 平台监测未完成",
      error instanceof Error ? error.message : "监测任务执行失败",
    );
  },
});

const selectedSample = computed(
  () =>
    batchQuery.data.value?.samples.find(
      (item) => item.id === selectedSampleId.value,
    ) ?? null,
);
watch(selectedSample, (sample) => {
  createdActionId.value = "";
  manualAnswer.value = sample?.raw_answer ?? "";
  manualFailed.value = sample?.status === "failed";
  manualFailureReason.value = sample?.failure_reason ?? "";
  const evaluation = sample?.evaluation;
  reviewState.value = {
    brand_found: evaluation?.brand_found ?? false,
    correctly_associated: evaluation?.correctly_associated ?? false,
    recommended: evaluation?.recommended ?? false,
    recommendation_supported: evaluation?.recommendation_supported ?? null,
    facts_accurate: evaluation?.facts_accurate ?? null,
    note: evaluation?.note ?? "",
  };
});

const manualMutation = useMutation({
  mutationFn: async () => {
    const sample = selectedSample.value;
    const batch = batchQuery.data.value;
    if (!sample || !batch) throw new Error("请选择人工采样问题");
    await saveManualSamples(batch.id, [
      {
        sample_id: sample.id,
        status: manualFailed.value ? "failed" : "succeeded",
        raw_answer: manualFailed.value ? undefined : manualAnswer.value,
        failure_reason: manualFailed.value
          ? manualFailureReason.value
          : undefined,
        asked_at: new Date().toISOString(),
      },
    ]);
  },
  onSuccess: async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["monitoring", clientId.value],
      }),
      queryClient.invalidateQueries({
        queryKey: ["monitoring-metrics", clientId.value],
      }),
    ]);
  },
});

const reviewMutation = useMutation({
  mutationFn: async () => {
    const sample = selectedSample.value;
    if (!sample || sample.status !== "succeeded")
      throw new Error("请选择已取得回答的样本");
    const evaluation = sample.evaluation;
    return updateMonitoringEvaluation(sample.id, {
      version: evaluation?.version ?? null,
      brand_found: reviewState.value.brand_found,
      correctly_associated: reviewState.value.correctly_associated,
      recommended: reviewState.value.recommended,
      recommendation_supported: reviewState.value.recommended
        ? reviewState.value.recommendation_supported
        : null,
      facts_accurate: reviewState.value.facts_accurate,
      source_visible: evaluation?.source_visible ?? false,
      mentioned_name: reviewState.value.brand_found
        ? (clientQuery.data.value?.standard_name ?? null)
        : null,
      reasons: evaluation?.reasons ?? [],
      incorrect_facts: evaluation?.incorrect_facts ?? [],
      visible_sources: evaluation?.visible_sources ?? [],
      note: reviewState.value.note || null,
    });
  },
  onSuccess: async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["monitoring", clientId.value],
      }),
      queryClient.invalidateQueries({
        queryKey: ["monitoring-metrics", clientId.value],
      }),
    ]);
  },
});
type SuggestedAction = NonNullable<
  MonitoringEvaluationData["suggested_actions"]
>[number];
const feedbackMutation = useMutation({
  mutationFn: async (action: SuggestedAction) => {
    const evaluation = selectedEvaluation.value;
    if (!evaluation) throw new Error("当前样本还没有评估结果");
    return createMonitoringFeedback(evaluation.id, {
      action_type: action.action_type,
      reason: action.reason,
      target_page: action.target_page,
    });
  },
  onSuccess: async (result) => {
    createdActionId.value = result.converted_record_id;
    await queryClient.invalidateQueries({
      queryKey: ["optimization-actions", clientId.value],
    });
  },
});

const metrics = computed(() => {
  return metricsQuery.data.value?.mode_breakdown?.[metricMode.value] ?? null;
});
const metricFraction = (key: string): string => {
  const detail = metrics.value?.metric_details[key];
  if (
    detail?.numerator === null ||
    detail?.numerator === undefined ||
    detail.denominator === null ||
    detail.denominator === undefined
  )
    return "— / —";
  return `${detail.numerator} / ${detail.denominator}`;
};
const metricTimeRange = computed(() => {
  const range = metricsQuery.data.value?.time_range;
  if (!range) return `${metricsFrom} 至 ${metricsTo}`;
  return `${range.from} 至 ${range.to}`;
});
const targetPageMap = {
  P02: { label: "企业知识库", path: "/knowledge" },
  P04: { label: "关键词与内容计划", path: "/strategy" },
  P06: { label: "渠道配置", path: "/channels" },
  P07: { label: "AI 可见性监测", path: "/monitoring" },
} as const;
const actionTarget = (targetPage: string) =>
  targetPageMap[targetPage as keyof typeof targetPageMap] ?? targetPageMap.P04;
const actionLink = (targetPage: string, actionId: string) => {
  const target = actionTarget(targetPage);
  return {
    path: target.path,
    query: { clientId: clientId.value, actionId },
  };
};
const openActions = computed(
  () => actionsQuery.data.value?.items.slice(0, 6) ?? [],
);
const rate = (value: number | null | undefined): string =>
  value === null || value === undefined ? "样本不足" : `${value}%`;
const platformMap = computed(
  () =>
    new Map(
      (platformsQuery.data.value?.items ?? []).map((item) => [item.id, item]),
    ),
);
const sampleGroups = computed(() => {
  const samples = batchQuery.data.value?.samples ?? [];
  const visible = samples.filter((sample) => {
    if (sampleFilter.value === "manual")
      return sample.collection_mode === "manual_consumer";
    if (sampleFilter.value === "attention")
      return (
        sample.status !== "succeeded" ||
        sample.evaluation?.brand_found === false ||
        sample.evaluation?.correctly_associated === false ||
        sample.evaluation?.recommended === false ||
        sample.evaluation?.facts_accurate === false
      );
    return true;
  });
  const groups = new Map<string, MonitoringSampleData[]>();
  for (const sample of visible) {
    groups.set(sample.platform_id, [
      ...(groups.get(sample.platform_id) ?? []),
      sample,
    ]);
  }
  return [...groups.entries()].map(([platformId, items]) => ({
    platformId,
    platform: platformMap.value.get(platformId),
    items,
    effective: items.filter((item) => item.status === "succeeded").length,
    attention: items.filter(
      (item) =>
        item.status !== "succeeded" ||
        item.evaluation?.brand_found === false ||
        item.evaluation?.recommended === false,
    ).length,
  }));
});
const familyLabel: Record<MonitoringSampleData["question_family"], string> = {
  category_discovery: "品类发现",
  recommendation: "推荐决策",
  scenario: "场景咨询",
  comparison: "选择比较",
  brand_verification: "品牌核验",
};
const formatTime = (value: string | null): string =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "尚未采样";
const statusLabel = (sample: MonitoringSampleData): string =>
  sample.status === "succeeded"
    ? sample.evaluation?.brand_found
      ? "已发现品牌"
      : "成功 · 未提及"
    : sample.status === "failed"
      ? "采样失败"
      : "等待人工采样";
const selectedEvaluation = computed<MonitoringEvaluationData | null>(
  () => selectedSample.value?.evaluation ?? null,
);
</script>

<template>
  <AppShell>
    <main class="workspace monitoring-page monitoring-workbench">
      <header class="page-head monitoring-hero">
        <div>
          <p class="eyebrow">P07 · AI 可见性监测</p>
          <h1>看见品牌是否真正进入 AI 回答</h1>
          <p>
            DeepSeek、通义千问自动采样，其他平台由你在消费者端提问后粘贴回答；失败不会被误算成未提及。
          </p>
        </div>
        <div v-if="clientId" class="monitoring-hero-actions">
          <span class="live-indicator"
            ><i></i
            >{{ batchQuery.data.value ? "已有监测基线" : "等待首轮监测" }}</span
          >
          <button
            class="button primary monitor-primary-action"
            :disabled="
              startMutation.isPending.value ||
              !monitoringReady ||
              (platformSelectionInitialized && !selectedPlatformCount)
            "
            @click="startMutation.mutate()"
          >
            {{
              startMutation.isPending.value
                ? "正在执行监测…"
                : batchQuery.data.value
                  ? "开始新一轮监测"
                  : "开始首轮监测"
            }}
          </button>
        </div>
      </header>

      <section v-if="!clientId" class="panel empty-panel monitoring-empty">
        <span class="empty-orbit">测</span>
        <h2>先选择一个客户</h2>
        <p>先在关键词与内容计划中确认问题，再用冻结问题建立监测基线。</p>
      </section>

      <template v-else>
        <section
          v-if="
            !batchQuery.data.value &&
            !questionSetsQuery.isPending.value &&
            !strategyQuery.isPending.value
          "
          class="monitoring-preparation"
          :class="{ ready: monitoringReady }"
        >
          <div>
            <strong>{{
              monitoringReady
                ? "首轮监测问题已经准备好"
                : "还没有可用于监测的问题"
            }}</strong>
            <p v-if="frozenQuestionSet">
              已冻结 {{ frozenQuestionSet.questions.length }}
              个监测问题，可以直接开始首轮监测。
            </p>
            <p v-else-if="baselineQuestions.length">
              已勾选 {{ selectedKeywordCount }} 个关键词，首轮将按用户意图选取
              {{ baselineQuestions.length }} 个代表问题；单个平台每题采样1次。
            </p>
            <p v-else>
              请先生成关键词，并勾选1—{{ BASELINE_QUESTION_LIMIT }}
              个用户真正可能向AI提问的问题。
            </p>
          </div>
          <RouterLink
            class="button secondary"
            :to="{ name: 'strategy', query: { clientId } }"
          >
            {{ monitoringReady ? "查看监测关键词" : "去生成并选择关键词" }}
          </RouterLink>
        </section>

        <p v-if="startMutation.isError.value" class="inline-error" role="alert">
          {{
            startMutation.error.value instanceof Error
              ? startMutation.error.value.message
              : "监测任务启动失败"
          }}
        </p>

        <div class="monitoring-mode-switch" aria-label="监测口径">
          <span>指标口径</span>
          <button
            :class="{ active: metricMode === 'api' }"
            @click="metricMode = 'api'"
          >
            API 自动样本
          </button>
          <button
            :class="{ active: metricMode === 'manual_consumer' }"
            @click="metricMode = 'manual_consumer'"
          >
            消费者端人工样本
          </button>
          <small>两种采集方式分别计算，不混合分母</small>
        </div>
        <p v-if="metricsQuery.isError.value" class="inline-error" role="alert">
          最近 30 天指标暂时无法载入，当前不会用最新批次冒充时间范围指标。
        </p>

        <section class="monitoring-overview">
          <article class="monitoring-score-card">
            <div class="score-card-top">
              <div>
                <span>无品牌问题发现率</span>
                <strong>{{ rate(metrics?.brand_found_rate) }}</strong>
              </div>
              <div
                class="score-ring"
                :style="{
                  '--score': `${metrics?.brand_found_rate ?? 0}%`,
                }"
              >
                <span>{{ metrics?.effective_sample_count ?? 0 }}</span>
                <small>有效样本</small>
              </div>
            </div>
            <p>
              当前仅统计{{
                metricMode === "api" ? " API 自动" : "消费者端人工"
              }}样本。失败 {{ metrics?.failed_count ?? 0 }} 条，未执行
              {{ metrics?.not_executed_count ?? 0 }} 条均单独记录。
            </p>
            <small class="metric-fraction"
              >发现 {{ metricFraction("discovery") }}（命中 / 有效）</small
            >
          </article>
          <article class="monitoring-kpi-card">
            <span>正确关联</span>
            <strong>{{ rate(metrics?.correct_association_rate) }}</strong>
            <small
              ><b>{{ metricFraction("correct_association") }}</b
              >名称与地区 / 服务相符</small
            >
          </article>
          <article class="monitoring-kpi-card">
            <span>进入推荐</span>
            <strong>{{ rate(metrics?.recommendation_rate) }}</strong>
            <small
              ><b>{{ metricFraction("recommendation") }}</b
              >回答中形成推荐表达</small
            >
          </article>
          <article class="monitoring-kpi-card">
            <span>事实准确</span>
            <strong>{{ rate(metrics?.fact_accuracy_rate) }}</strong>
            <small
              ><b>{{ metricFraction("fact_accuracy") }}</b
              >仅统计已依据知识库核验的样本</small
            >
          </article>
          <article class="monitoring-kpi-card repeat-kpi">
            <span>核心问题重复出现</span>
            <strong>{{ rate(metrics?.repeat_appearance_rate) }}</strong>
            <small
              ><b>{{ metricFraction("repeat_appearance") }}</b
              >同一 P1 问题至少两次采样</small
            >
          </article>
        </section>

        <section class="monitoring-context-strip">
          <div>
            <span>统计时间范围</span>
            <strong>{{ metricTimeRange }}</strong>
          </div>
          <div>
            <span>样本状态</span>
            <strong
              >有效 {{ metrics?.effective_sample_count ?? 0 }} · 失败
              {{ metrics?.failed_count ?? 0 }} · 未执行
              {{ metrics?.not_executed_count ?? 0 }}</strong
            >
          </div>
          <div>
            <span>最近完成 / 固定问题</span>
            <strong
              >{{ formatTime(batchQuery.data.value?.completed_at ?? null) }}
              ·
              {{
                questionSetsQuery.data.value?.items[0]?.questions?.length ?? 0
              }}
              题</strong
            >
          </div>
          <div class="context-warning">
            <span>口径说明</span>
            <strong>API 回答 ≠ 消费者端回答</strong>
          </div>
        </section>

        <section class="monitoring-catalog-section">
          <header class="section-heading">
            <div>
              <p class="eyebrow">平台覆盖</p>
              <h2>国内主流 AI 监测目录</h2>
            </div>
            <small
              >已选 {{ selectedPlatformCount }} 个 · 目录版本
              {{ platformsQuery.data.value?.catalog_version ?? "—" }}</small
            >
          </header>
          <div class="platform-selection-toolbar">
            <div>
              <strong>选择本轮监测平台</strong>
              <span
                >默认覆盖 P0 与 P1；API
                自动采样，消费者平台生成待人工粘贴任务。</span
              >
            </div>
            <div>
              <button
                class="button"
                type="button"
                @click="selectPlatformScope('all')"
              >
                全部主流平台
              </button>
              <button
                class="button"
                type="button"
                @click="selectPlatformScope('P0')"
              >
                仅核心 P0
              </button>
            </div>
          </div>
          <div class="platform-rail">
            <article
              v-for="platform in platformsQuery.data.value?.items ?? []"
              :key="platform.id"
              class="platform-chip-card"
              :class="{
                api: platform.mode === 'api',
                selected: selectedPlatformIds.includes(platform.id),
              }"
            >
              <button
                class="platform-select-button"
                type="button"
                :aria-label="`${selectedPlatformIds.includes(platform.id) ? '取消选择' : '选择'}${platform.name}`"
                :aria-pressed="selectedPlatformIds.includes(platform.id)"
                @click="togglePlatform(platform.id)"
              >
                <span class="platform-avatar">{{
                  platform.name.slice(0, 1)
                }}</span>
                <span>
                  <strong>{{ platform.name }}</strong>
                  <small>{{ platform.mode_label }}</small>
                </span>
                <i>{{ platform.priority }}</i>
                <b class="platform-check" aria-hidden="true">{{
                  selectedPlatformIds.includes(platform.id) ? "✓" : "+"
                }}</b>
              </button>
              <a
                v-if="platform.consumer_entry_url"
                class="platform-entry-link"
                :href="platform.consumer_entry_url"
                target="_blank"
                rel="noreferrer"
                >打开官方入口 ↗</a
              >
              <span v-else class="platform-entry-link"
                >由官方 API 自动采样</span
              >
            </article>
          </div>
        </section>

        <section
          v-if="openActions.length || actionsQuery.isPending.value"
          class="monitoring-actions-section"
        >
          <header class="section-heading">
            <div>
              <p class="eyebrow">改进闭环</p>
              <h2>监测结果已转成可执行任务</h2>
            </div>
            <small>按最新创建时间展示</small>
          </header>
          <div v-if="actionsQuery.isPending.value" class="action-task-loading">
            正在载入改进任务…
          </div>
          <div v-else class="action-task-grid">
            <article
              v-for="action in openActions"
              :key="action.id"
              class="action-task-card"
            >
              <div>
                <span
                  >{{ action.target_level }} · {{ action.target_page }}</span
                >
                <small>{{ formatTime(action.created_at) }}</small>
              </div>
              <strong>{{ action.title }}</strong>
              <p>{{ action.reason }}</p>
              <RouterLink
                class="action-task-link"
                :to="actionLink(action.target_page, action.id)"
              >
                去{{ actionTarget(action.target_page).label }}执行
                <span>→</span>
              </RouterLink>
            </article>
          </div>
        </section>

        <section
          v-if="batchQuery.isPending.value"
          class="panel loading-panel monitoring-loading"
          aria-busy="true"
        >
          <span class="loading-pulse"></span>
          <div>
            <h2>正在载入监测结果</h2>
            <p>正在汇总平台与问题样本。</p>
          </div>
        </section>
        <section
          v-else-if="batchQuery.isError.value"
          class="panel error-panel"
          role="alert"
        >
          <h2>监测结果暂时无法载入</h2>
          <button class="button" @click="batchQuery.refetch()">重新载入</button>
        </section>
        <section
          v-else-if="!batchQuery.data.value"
          class="monitoring-start-card"
        >
          <div class="start-card-visual">
            <span>01</span><i></i><span>02</span><i></i><span>03</span>
          </div>
          <div>
            <p class="eyebrow">首轮基线</p>
            <h2>用同一组问题，建立可比较的监测基线</h2>
            <p>
              使用 P04 已确认并锁定的问题。系统先执行 DeepSeek
              、通义千问和豆包生成官方模型 API
              自动样本，不再创建消费者端人工采样清单。
            </p>
          </div>
          <button
            class="button primary"
            :disabled="
              startMutation.isPending.value ||
              (platformSelectionInitialized && !selectedPlatformCount)
            "
            @click="startMutation.mutate()"
          >
            生成问题并开始
          </button>
        </section>

        <template v-else>
          <section class="monitoring-results-head">
            <div>
              <p class="eyebrow">样本明细</p>
              <h2>逐条回答与判断</h2>
            </div>
            <div class="segmented-control">
              <button
                v-for="option in [
                  ['all', '全部样本'],
                  ['attention', '需要关注'],
                  ['manual', '人工采样'],
                ] as const"
                :key="option[0]"
                :class="{ active: sampleFilter === option[0] }"
                @click="sampleFilter = option[0]"
              >
                {{ option[1] }}
              </button>
            </div>
          </section>

          <div class="monitoring-results-layout">
            <section class="monitoring-platform-groups">
              <article
                v-for="group in sampleGroups"
                :key="group.platformId"
                class="monitor-platform-panel"
              >
                <header>
                  <div>
                    <span class="platform-avatar">{{
                      group.platform?.name.slice(0, 1) ?? "AI"
                    }}</span>
                    <span
                      ><strong>{{
                        group.platform?.name ?? group.platformId
                      }}</strong
                      ><small>{{
                        group.platform?.mode_label ?? "监测样本"
                      }}</small></span
                    >
                  </div>
                  <p>
                    <b>{{ group.effective }}</b> 条有效
                    <span v-if="group.attention"
                      >· {{ group.attention }} 条需关注</span
                    >
                  </p>
                </header>
                <div class="sample-card-list">
                  <button
                    v-for="sample in group.items"
                    :key="sample.id"
                    class="sample-row-card"
                    :class="{
                      selected: selectedSampleId === sample.id,
                      waiting: sample.status === 'not_executed',
                      failed: sample.status === 'failed',
                    }"
                    @click="selectedSampleId = sample.id"
                  >
                    <span class="family-pill">{{
                      familyLabel[sample.question_family]
                    }}</span>
                    <span class="sample-question">
                      <strong>{{ sample.question_text }}</strong>
                      <small
                        >第 {{ sample.attempt }} 次 ·
                        {{ formatTime(sample.asked_at) }}</small
                      >
                    </span>
                    <span class="sample-result" :data-state="sample.status">{{
                      statusLabel(sample)
                    }}</span>
                    <span class="row-arrow">›</span>
                  </button>
                </div>
              </article>
              <div v-if="!sampleGroups.length" class="monitoring-no-results">
                当前筛选下没有样本。
              </div>
            </section>

            <aside class="monitoring-detail-panel">
              <template v-if="selectedSample">
                <header>
                  <div>
                    <span class="family-pill">{{
                      familyLabel[selectedSample.question_family]
                    }}</span>
                    <h2>样本详情</h2>
                  </div>
                  <button
                    class="detail-close"
                    aria-label="关闭详情"
                    @click="selectedSampleId = ''"
                  >
                    ×
                  </button>
                </header>
                <div class="detail-question">
                  <small>监测问题</small>
                  <strong>{{ selectedSample.question_text }}</strong>
                </div>

                <template
                  v-if="
                    selectedSample.collection_mode === 'manual_consumer' &&
                    selectedSample.status === 'not_executed'
                  "
                >
                  <div class="manual-guide">
                    <span>1</span>
                    <p>
                      打开
                      <a
                        :href="
                          platformMap.get(selectedSample.platform_id)
                            ?.consumer_entry_url
                        "
                        target="_blank"
                        rel="noreferrer"
                        >{{ selectedSample.platform_name }} ↗</a
                      >，原样提问
                    </p>
                    <span>2</span>
                    <p>将完整回答粘贴到下方</p>
                  </div>
                  <label class="field-label" for="manual-answer"
                    >平台原始回答</label
                  >
                  <textarea
                    id="manual-answer"
                    v-model="manualAnswer"
                    rows="9"
                    placeholder="请粘贴完整回答，不要摘录或改写…"
                    :disabled="manualFailed"
                  ></textarea>
                  <label class="failure-toggle">
                    <input v-model="manualFailed" type="checkbox" />
                    <span>本次未取得回答，记录为采样失败</span>
                  </label>
                  <input
                    v-if="manualFailed"
                    v-model="manualFailureReason"
                    class="text-input"
                    placeholder="例如：平台无法加载、请求受限"
                  />
                  <p
                    v-if="manualMutation.isError.value"
                    class="inline-error"
                    role="alert"
                  >
                    {{
                      manualMutation.error.value instanceof Error
                        ? manualMutation.error.value.message
                        : "人工样本保存失败"
                    }}
                  </p>
                  <button
                    class="button primary detail-save"
                    :disabled="
                      manualMutation.isPending.value ||
                      (!manualFailed && !manualAnswer.trim()) ||
                      (manualFailed && !manualFailureReason.trim())
                    "
                    @click="manualMutation.mutate()"
                  >
                    {{
                      manualMutation.isPending.value
                        ? "正在分析回答…"
                        : "保存并自动分析"
                    }}
                  </button>
                </template>

                <template v-else-if="selectedSample.status === 'succeeded'">
                  <div class="raw-answer-card">
                    <small>平台原始回答</small>
                    <p>{{ selectedSample.raw_answer }}</p>
                  </div>
                  <div class="review-heading">
                    <div>
                      <small>判断结果</small>
                      <strong>{{
                        selectedEvaluation?.evaluator === "user"
                          ? "人工已复核"
                          : "系统初步判断"
                      }}</strong>
                    </div>
                    <span>{{
                      selectedEvaluation?.evaluator === "user"
                        ? "已校准"
                        : "可编辑"
                    }}</span>
                  </div>
                  <div class="review-checklist">
                    <label
                      ><input
                        v-model="reviewState.brand_found"
                        type="checkbox"
                      /><span
                        ><strong>出现客户名称</strong
                        ><small>标准名称或简称被提及</small></span
                      ></label
                    >
                    <label
                      ><input
                        v-model="reviewState.correctly_associated"
                        type="checkbox"
                      /><span
                        ><strong>关联正确</strong
                        ><small>地区与服务没有混淆</small></span
                      ></label
                    >
                    <label
                      ><input
                        v-model="reviewState.recommended"
                        type="checkbox"
                      /><span
                        ><strong>形成推荐</strong
                        ><small>不只是普通提及</small></span
                      ></label
                    >
                    <div class="review-tristate">
                      <span
                        ><strong>事实准确性</strong
                        ><small>须依据企业知识库与证据判断</small></span
                      >
                      <select v-model="reviewState.facts_accurate">
                        <option :value="null">待核验</option>
                        <option :value="true">准确</option>
                        <option :value="false">有误</option>
                      </select>
                    </div>
                    <div v-if="reviewState.recommended" class="review-tristate">
                      <span
                        ><strong>推荐理由是否有据</strong
                        ><small>是否可由 P02 事实与证据支持</small></span
                      >
                      <select v-model="reviewState.recommendation_supported">
                        <option :value="null">待核验</option>
                        <option :value="true">有依据</option>
                        <option :value="false">无依据</option>
                      </select>
                    </div>
                  </div>
                  <div
                    v-if="selectedEvaluation?.suggested_actions?.[0]"
                    class="monitoring-next-action"
                  >
                    <small>系统建议下一步</small>
                    <strong>{{
                      selectedEvaluation.suggested_actions[0].title
                    }}</strong>
                    <p>{{ selectedEvaluation.suggested_actions[0].reason }}</p>
                    <button
                      class="button"
                      :disabled="
                        feedbackMutation.isPending.value ||
                        Boolean(createdActionId)
                      "
                      @click="
                        feedbackMutation.mutate(
                          selectedEvaluation.suggested_actions[0],
                        )
                      "
                    >
                      {{
                        createdActionId
                          ? "已加入改进任务"
                          : feedbackMutation.isPending.value
                            ? "正在创建…"
                            : "加入下一轮改进"
                      }}
                    </button>
                    <RouterLink
                      v-if="createdActionId"
                      class="created-action-link"
                      :to="
                        actionLink(
                          selectedEvaluation.suggested_actions[0].target_page,
                          createdActionId,
                        )
                      "
                    >
                      已保存任务详情，去{{
                        targetPageMap[
                          selectedEvaluation.suggested_actions[0].target_page
                        ].label
                      }}执行 →
                    </RouterLink>
                  </div>
                  <label class="field-label" for="review-note">复核备注</label>
                  <textarea
                    id="review-note"
                    v-model="reviewState.note"
                    rows="3"
                    placeholder="可记录判断依据或需要补充的事实…"
                  ></textarea>
                  <p
                    v-if="reviewMutation.isError.value"
                    class="inline-error"
                    role="alert"
                  >
                    {{
                      reviewMutation.error.value instanceof Error
                        ? reviewMutation.error.value.message
                        : "复核结果保存失败"
                    }}
                  </p>
                  <button
                    class="button primary detail-save"
                    :disabled="reviewMutation.isPending.value"
                    @click="reviewMutation.mutate()"
                  >
                    {{
                      reviewMutation.isPending.value
                        ? "正在保存…"
                        : "保存复核结果"
                    }}
                  </button>
                </template>
                <div v-else class="failed-sample-detail">
                  <span>!</span>
                  <h3>
                    本次{{
                      selectedSample.collection_mode === "manual_consumer"
                        ? "人工"
                        : " API "
                    }}采样失败
                  </h3>
                  <p>
                    {{
                      selectedSample.failure_reason ??
                      "失败原因暂时不可用，可在下一轮重新采样。"
                    }}
                  </p>
                </div>
              </template>
              <template v-else>
                <div class="detail-placeholder">
                  <span>↗</span>
                  <h2>选择一条样本查看详情</h2>
                  <p>可查看原始回答、自动判断，或完成消费者端人工采样。</p>
                </div>
              </template>
            </aside>
          </div>
        </template>
      </template>
    </main>
  </AppShell>
</template>
