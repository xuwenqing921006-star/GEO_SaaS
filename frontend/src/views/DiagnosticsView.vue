<script setup lang="ts">
import { useMutation, useQuery } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { DiagnosticRunData } from "../api/dto";
import {
  formatJobProgress,
  pollJobUntilTerminal,
  STANDARD_JOB_POLLING_INTERVAL,
} from "../api/jobPolling";
import { createDiagnostic, getJob } from "../api/strategy";
import { getLatestDiagnostic } from "../api/knowledge";
import AppShell from "../components/AppShell.vue";
import { buildChannelActionPlan } from "../diagnosticAdviceLogic";
import {
  notifyRequestError,
  notifyRequestInfo,
  notifyRequestSuccess,
} from "../requestNotifications";
import { useWorkspaceStore } from "../stores/workspace";

const route = useRoute();
const router = useRouter();
const workspace = useWorkspaceStore();
const clientId = computed(() =>
  typeof route.query.clientId === "string"
    ? route.query.clientId
    : workspace.currentClientId,
);
const diagnosticQuery = useQuery({
  queryKey: computed(() => ["diagnostic", clientId.value]),
  queryFn: () => getLatestDiagnostic(clientId.value),
  enabled: computed(() => Boolean(clientId.value)),
});
const taskMessage = ref("");
const actionError = ref("");
const actionMessage = ref("");
let pollingGeneration = 0;
watch(clientId, () => {
  pollingGeneration += 1;
  taskMessage.value = "";
});

const waitForJob = async (jobId: string): Promise<void> => {
  const generation = ++pollingGeneration;
  const job = await pollJobUntilTerminal(() => getJob(jobId), {
    intervalMs: STANDARD_JOB_POLLING_INTERVAL,
    timeoutMs: 5 * 60_000,
    timeoutMessage: "GEO 诊断已等待 5 分钟仍未完成，请重新发起诊断",
    cancellationMessage: "GEO 诊断跟踪已取消",
    isCancelled: () => generation !== pollingGeneration,
    onUpdate: (current) => {
      taskMessage.value = formatJobProgress(current);
    },
  });
  if (job.status !== "succeeded")
    throw new Error(job.error_message ?? "诊断任务未完成");
  await diagnosticQuery.refetch();
  taskMessage.value = "";
};

const diagnosticMutation = useMutation({
  mutationFn: async () => {
    const accepted = await createDiagnostic(
      clientId.value,
      crypto.randomUUID(),
    );
    await waitForJob(accepted.job_id);
  },
  onMutate: () => {
    actionError.value = "";
    actionMessage.value = "";
    taskMessage.value = "正在读取企业资料、自动生成检测问题并调用四个平台…";
    notifyRequestInfo(
      "GEO 诊断已开始",
      "完成后会自动更新页面并通知，无需手动刷新",
    );
  },
  onSuccess: () => {
    actionMessage.value = "GEO 诊断完成，平台评分与优化建议已更新";
    notifyRequestSuccess("GEO 诊断完成", "平台评分与优化建议已更新");
  },
  onError: (error: unknown) => {
    actionError.value = error instanceof Error ? error.message : "GEO 诊断失败";
    taskMessage.value = "";
    notifyRequestError("GEO 诊断未完成", actionError.value);
  },
});

type PlatformResult = NonNullable<
  DiagnosticRunData["platform_results"]
>[number];
const diagnosis = computed(() => diagnosticQuery.data.value);
const platforms = computed(() => diagnosis.value?.platform_results ?? []);
const competitiveInsights = computed(
  () => diagnosis.value?.competitive_insights,
);
const channelActionPlan = computed(() =>
  buildChannelActionPlan(competitiveInsights.value?.channel_signals ?? []),
);
const suggestions = computed(() =>
  (diagnosis.value?.issues ?? [])
    .filter((item) => item.status === "open")
    .sort((left, right) => {
      const weight = { blocking: 0, warning: 1, info: 2 };
      return weight[left.severity] - weight[right.severity];
    })
    .slice(0, 6),
);
const gradeLabel: Record<string, string> = {
  excellent: "优",
  good: "良",
  medium: "中",
  poor: "差",
};
const statusLabel: Record<PlatformResult["status"], string> = {
  unconfigured: "未配置",
  untested: "未检测",
  failed: "检测失败",
  not_found: "未发现",
  brand_only: "仅品牌词可见",
  mentioned: "已提及",
  associated: "正确关联",
  recommended: "推荐出现",
};
const sourceCapabilityLabel = (
  capability: PlatformResult["source_capability"],
): string => {
  if (capability === "available") return "已取得来源";
  if (capability === "not_supported") return "接口不提供来源";
  return "本次未返回来源";
};
const formatDateTime = (value: string | null | undefined): string =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";
const openKeywords = (): void => {
  void router.push({ name: "strategy", query: { clientId: clientId.value } });
};
const openChannels = (): void => {
  void router.push({ name: "channels", query: { clientId: clientId.value } });
};
const probeQuestions = computed(() => platforms.value[0]?.questions ?? []);
</script>

<template>
  <AppShell>
    <main class="workspace diagnosis-page">
      <header class="page-head page-head--action">
        <div>
          <p class="eyebrow">AI VISIBILITY · GEO 诊断</p>
          <h1>GEO 诊断</h1>
          <p>
            根据企业知识库自动生成检测问题，并判断品牌在四个主流 AI
            平台回答中的可见程度。
          </p>
        </div>
        <button
          v-if="clientId"
          class="button primary"
          :disabled="diagnosticMutation.isPending.value"
          @click="diagnosticMutation.mutate()"
        >
          {{ diagnosis ? "重新计算诊断" : "开始诊断" }}
        </button>
      </header>

      <p v-if="taskMessage" class="task-banner" aria-live="polite">
        <span class="task-pulse" />{{ taskMessage }}
      </p>
      <p v-if="actionError" class="inline-error" role="alert">
        {{ actionError }}
      </p>
      <p v-if="actionMessage" class="inline-success" role="status">
        {{ actionMessage }}
      </p>

      <section v-if="!clientId" class="panel empty-panel">
        <h2>请先选择客户</h2>
        <p>选择客户后，系统才能读取对应的地区、行业、主营业务和企业介绍。</p>
      </section>
      <section
        v-else-if="diagnosticQuery.isPending.value"
        class="panel loading-panel"
        aria-busy="true"
      >
        <span class="loading-orbit" />
        <h2>正在读取诊断结果</h2>
        <p>正在整理各平台收录情况与 GEO 建议…</p>
      </section>
      <section
        v-else-if="diagnosticQuery.isError.value"
        class="panel error-panel"
        role="alert"
      >
        <h2>诊断结果暂时无法载入</h2>
        <p>请检查服务后重试，不会使用其他客户的数据替代。</p>
        <button class="button primary" @click="diagnosticQuery.refetch()">
          重新载入
        </button>
      </section>
      <section v-else-if="!diagnosis" class="panel diagnosis-empty">
        <div class="diagnosis-empty__icon">AI</div>
        <div>
          <h2>还没有 GEO 诊断结果</h2>
          <p>
            系统会读取地区、行业、主营业务、品牌和客群，自动生成问题并检测
            DeepSeek、通义千问、豆包和文心一言。
          </p>
        </div>
        <button class="button primary" @click="diagnosticMutation.mutate()">
          开始首次诊断
        </button>
      </section>
      <section
        v-else-if="diagnosis.status === 'failed'"
        class="panel error-panel"
        role="alert"
      >
        <h2>上一次诊断未完成</h2>
        <p>失败结果不会显示历史评分。请重新诊断，或检查平台检测与模型连接。</p>
        <button class="button primary" @click="diagnosticMutation.mutate()">
          重新诊断
        </button>
      </section>

      <template v-else>
        <section v-if="diagnosis.is_stale" class="stale-notice" role="status">
          <div>
            <strong>企业知识库已经更新</strong>
            <p>
              当前结果来自旧资料，已有 {{ diagnosis.changed_fact_count }}
              项信息变化，建议重新诊断。
            </p>
          </div>
          <button class="button primary" @click="diagnosticMutation.mutate()">
            立即更新诊断
          </button>
        </section>

        <section
          v-if="(diagnosis.effective_sample_count ?? 0) === 0"
          class="panel diagnostic-sample-notice"
          role="status"
        >
          <div>
            <strong>当前没有可用于评分的自动检测回答</strong>
            <p>
              请先在系统设置中配置相应平台 API。未配置、超时或请求失败都不会按 0
              分处理，也不会被误判为企业没有被平台收录。
            </p>
          </div>
          <button
            class="button primary"
            @click="
              router.push({
                name: 'settings',
                query: { clientId: clientId },
              })
            "
          >
            配置平台 API
          </button>
        </section>

        <section class="diagnosis-summary">
          <article class="panel diagnosis-score-card">
            <span>综合评分</span>
            <div class="diagnosis-score">
              <strong>{{ diagnosis.overall_score ?? "—" }}</strong>
              <small>/ 100</small>
            </div>
            <p v-if="diagnosis.overall_grade">
              当前等级
              <b :class="`grade grade--${diagnosis.overall_grade}`">
                {{ gradeLabel[diagnosis.overall_grade] }}
              </b>
            </p>
            <p v-else>暂无足够的自动检测回答</p>
          </article>
          <article class="panel diagnosis-metric-card">
            <span>已检测平台</span>
            <strong>
              {{ diagnosis.evaluated_platform_count ?? 0 }}
              <small
                >/
                {{ diagnosis.total_platform_count ?? platforms.length }}</small
              >
            </strong>
            <p>只统计成功返回并完成评估的平台</p>
          </article>
          <article class="panel diagnosis-metric-card">
            <span>有效自动回答</span>
            <strong>{{ diagnosis.effective_sample_count ?? 0 }}</strong>
            <p>每个平台自动检测 3 类问题</p>
          </article>
          <article class="panel diagnosis-metric-card">
            <span>诊断时间</span>
            <strong class="diagnosis-date">
              {{ formatDateTime(diagnosis.completed_at) }}
            </strong>
            <p>企业资料更新后应重新诊断</p>
          </article>
        </section>

        <section class="panel diagnosis-platforms">
          <header class="panel-header">
            <div>
              <h2>AI 平台收录与推荐表现</h2>
              <p>
                评分由品牌出现 30%、正确关联 25%、推荐命中 25%、可核验事实 15%
                和可见来源 5% 组成。
              </p>
            </div>
          </header>
          <div v-if="probeQuestions.length" class="diagnosis-probe-questions">
            <span>本次自动检测问题</span>
            <div>
              <p v-for="question in probeQuestions" :key="question.id">
                <b>{{ question.label }}</b
                >{{ question.text }}
              </p>
            </div>
          </div>
          <div class="data-table-wrap">
            <table class="data-table platform-result-table">
              <caption class="sr-only">
                各 AI 平台 GEO 诊断结果
              </caption>
              <thead>
                <tr>
                  <th>AI 平台</th>
                  <th>收录状态</th>
                  <th>评分</th>
                  <th>级别</th>
                  <th>有效回答</th>
                  <th>来源证据</th>
                  <th>评语</th>
                  <th>最近检测</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="platform in platforms" :key="platform.platform_id">
                  <td>
                    <strong>{{ platform.platform_name }}</strong>
                    <small> API 自动检测 </small>
                  </td>
                  <td>
                    <span
                      :class="`status-pill status-pill--${platform.status}`"
                    >
                      {{ statusLabel[platform.status] }}
                    </span>
                  </td>
                  <td class="platform-score">
                    {{ platform.score ?? "—" }}
                  </td>
                  <td>
                    <b
                      v-if="platform.grade"
                      :class="`grade grade--${platform.grade}`"
                    >
                      {{ gradeLabel[platform.grade] }}
                    </b>
                    <span v-else>—</span>
                  </td>
                  <td>{{ platform.valid_sample_count }}</td>
                  <td class="platform-source-status">
                    <strong>{{ platform.source_count ?? 0 }} 条</strong>
                    <small>{{
                      sourceCapabilityLabel(platform.source_capability)
                    }}</small>
                  </td>
                  <td class="platform-comment">
                    <p>{{ platform.comment }}</p>
                    <details
                      v-if="
                        platform.questions?.some(
                          (question) => question.answer_excerpt,
                        )
                      "
                    >
                      <summary>查看回答摘要</summary>
                      <div
                        v-for="question in platform.questions"
                        :key="question.id"
                      >
                        <strong>{{ question.label }}</strong>
                        <span>{{
                          question.answer_excerpt ?? "本题请求未成功"
                        }}</span>
                        <ul
                          v-if="question.sources?.length"
                          class="answer-sources"
                        >
                          <li
                            v-for="source in question.sources"
                            :key="source.url"
                          >
                            <a
                              :href="source.url"
                              target="_blank"
                              rel="noopener noreferrer"
                              >{{ source.title }}</a
                            >
                          </li>
                        </ul>
                      </div>
                    </details>
                  </td>
                  <td>{{ formatDateTime(platform.measured_at) }}</td>
                </tr>
                <tr v-if="platforms.length === 0">
                  <td colspan="8" class="table-empty">
                    暂无平台检测结果，请重新开始诊断。
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="diagnosis-note">
            系统调用各平台官方 API，不自动登录消费者 App。API
            回答用于形成可重复的运营基线，不保证与消费者 App
            的每次回答完全一致；未配置和失败平台不进入综合评分。
          </p>
        </section>

        <section class="panel geo-advice-panel">
          <header class="panel-header">
            <div>
              <h2>下一步优化建议</h2>
              <p>根据本次检测结果，只保留可以直接执行的渠道和内容动作。</p>
            </div>
            <div class="panel-actions">
              <button class="button" type="button" @click="openChannels">
                配置发布平台
              </button>
              <button
                class="button primary"
                type="button"
                :disabled="diagnosis.is_stale"
                @click="openKeywords"
              >
                生成关键词
              </button>
            </div>
          </header>
          <div
            v-if="channelActionPlan.length || suggestions.length"
            class="geo-advice-list"
          >
            <article
              v-for="(item, index) in channelActionPlan"
              :key="item.channelId"
            >
              <span class="advice-index">{{ index + 1 }}</span>
              <div>
                <div class="advice-title">
                  <strong>{{ item.title }}</strong>
                  <span class="severity severity--info"> 本次结果建议 </span>
                </div>
                <p>{{ item.description }}</p>
                <small>建议行动：{{ item.action }}</small>
              </div>
            </article>
            <article
              v-for="(item, index) in suggestions.slice(0, 3)"
              :key="item.id"
            >
              <span class="advice-index">{{
                channelActionPlan.length + index + 1
              }}</span>
              <div>
                <div class="advice-title">
                  <strong>{{ item.title }}</strong>
                  <span :class="`severity severity--${item.severity}`">
                    {{
                      item.severity === "blocking"
                        ? "优先"
                        : item.severity === "warning"
                          ? "建议"
                          : "优化"
                    }}
                  </span>
                </div>
                <p>{{ item.explanation }}</p>
                <small>建议行动：{{ item.suggested_action }}</small>
              </div>
            </article>
          </div>
          <div v-else class="empty-inline">
            <strong>当前没有明显的 GEO 阻碍</strong>
            <p>建议保持内容更新，并定期复测各平台的推荐表现。</p>
          </div>
          <p v-if="channelActionPlan.length" class="methodology-note">
            渠道建议用于确定下一步运营动作，不代表任何 AI 平台公开或内部权重。
          </p>
        </section>
      </template>
    </main>
  </AppShell>
</template>
