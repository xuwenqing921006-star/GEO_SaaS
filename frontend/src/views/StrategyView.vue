<script setup lang="ts">
import { useMutation, useQuery } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import type {
  ConfirmedKeywordData,
  KeywordCandidateData,
  KeywordGenerationData,
  KeywordType,
} from "../api/dto";
import { ApiError } from "../api/http";
import {
  formatJobProgress,
  pollJobUntilTerminal,
  STANDARD_JOB_POLLING_INTERVAL,
} from "../api/jobPolling";
import {
  archiveKeywordGeneration,
  confirmKeywordGeneration,
  createKeywordGeneration,
  getJob,
  getKeywordGeneration,
  getKeywordWorkspace,
  saveKeywordProfile,
  updateKeywordCandidate,
  updateStrategyItem,
} from "../api/strategy";
import AppShell from "../components/AppShell.vue";
import ModalDialog from "../components/ModalDialog.vue";
import {
  notifyRequestError,
  notifyRequestInfo,
  notifyRequestSuccess,
} from "../requestNotifications";
import { useWorkspaceStore } from "../stores/workspace";

const route = useRoute();
const workspace = useWorkspaceStore();
const clientId = computed(() =>
  typeof route.query.clientId === "string"
    ? route.query.clientId
    : workspace.currentClientId,
);
const queryEnabled = computed(() => Boolean(clientId.value));
const workspaceQuery = useQuery({
  queryKey: computed(() => ["keyword-workspace", clientId.value]),
  queryFn: () => getKeywordWorkspace(clientId.value),
  enabled: queryEnabled,
});

const primaryKeyword = ref("");
const regions = ref<string[]>([]);
const secondaryKeywords = ref<string[]>([]);
const selectedTypes = ref<KeywordType[]>([]);
const targetCount = ref(12);
const regionDraft = ref("");
const secondaryDraft = ref("");
const actionError = ref("");
const jobMessage = ref("");
const hydratedProfileKey = ref("");
const detailGeneration = ref<KeywordGenerationData | null>(null);
const deleteTaskTarget = ref<KeywordGenerationData | null>(null);
const deleteKeywordTarget = ref<ConfirmedKeywordData | null>(null);
const candidateBusy = ref(false);
let pollGeneration = 0;
let followedJobId = "";

const keywordTypeLabel: Record<KeywordType, string> = {
  local_service: "地区主营",
  brand: "企业品牌",
  recommendation: "推荐决策",
  scenario: "场景适配",
  service_detail: "服务细分",
  comparison: "选择比较",
  transaction: "费用流程",
  trust: "信任核验",
};
const keywordTypeDescription: Record<KeywordType, string> = {
  local_service: "地区 + 核心业务的发现问题",
  brand: "用户直接了解企业或品牌",
  recommendation: "哪家好、推荐一家等决策问题",
  scenario: "年龄、基础、目标等具体场景",
  service_detail: "课程、项目与服务内容",
  comparison: "选择标准和方案比较",
  transaction: "费用、流程、预约与咨询",
  trust: "企业信息、服务范围与可信核验",
};
const keywordTypes = Object.entries(keywordTypeLabel) as [
  KeywordType,
  string,
][];
const generationStatusLabel: Record<KeywordGenerationData["status"], string> = {
  queued: "等待生成",
  running: "生成中",
  awaiting_confirmation: "待确认",
  confirmed: "已保存",
  failed: "生成失败",
};

watch(
  () => workspaceQuery.data.value?.profile,
  (profile) => {
    if (!profile) return;
    const profileKey = `${clientId.value}:${profile.version}:${profile.knowledge_fingerprint}`;
    if (profileKey === hydratedProfileKey.value) return;
    hydratedProfileKey.value = profileKey;
    primaryKeyword.value = profile.primary_keyword;
    regions.value = [...profile.regions];
    secondaryKeywords.value = [...profile.secondary_keywords];
    selectedTypes.value = [...profile.keyword_types];
    targetCount.value = profile.recommended_count;
  },
  { immediate: true },
);
watch(clientId, () => {
  pollGeneration += 1;
  followedJobId = "";
  hydratedProfileKey.value = "";
  detailGeneration.value = null;
  actionError.value = "";
  jobMessage.value = "";
});

const profile = computed(() => workspaceQuery.data.value?.profile);
const generations = computed(
  () => workspaceQuery.data.value?.generations ?? [],
);
const confirmedKeywords = computed(
  () => workspaceQuery.data.value?.confirmed_keywords ?? [],
);
const activeCandidates = computed(
  () => detailGeneration.value?.candidates?.filter((item) => item.active) ?? [],
);
const selectedCandidateIds = computed(() =>
  activeCandidates.value.filter((item) => item.selected).map((item) => item.id),
);
const allCandidatesSelected = computed(
  () =>
    activeCandidates.value.length > 0 &&
    selectedCandidateIds.value.length === activeCandidates.value.length,
);
const profileIsValid = computed(
  () =>
    primaryKeyword.value.trim().length >= 2 &&
    regions.value.length >= 1 &&
    regions.value.length <= 5 &&
    secondaryKeywords.value.length <= 10 &&
    selectedTypes.value.length >= 1 &&
    targetCount.value >= 5 &&
    targetCount.value <= 50,
);

const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof ApiError || error instanceof Error
    ? error.message
    : fallback;
const formatDateTime = (value: string): string =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

const addTag = (
  draft: typeof regionDraft,
  values: typeof regions,
  limit: number,
  label: string,
): void => {
  const value = draft.value.replace(/[,，、;；]+$/g, "").trim();
  actionError.value = "";
  if (!value) return;
  if (values.value.includes(value)) {
    actionError.value = `${label}“${value}”已存在`;
    return;
  }
  if (values.value.length >= limit) {
    actionError.value = `${label}最多添加 ${limit} 个`;
    return;
  }
  values.value = [...values.value, value];
  draft.value = "";
};
const removeTag = (values: typeof regions, index: number): void => {
  values.value = values.value.filter((_, current) => current !== index);
};
const addRegion = (): void => addTag(regionDraft, regions, 5, "地区");
const addSecondaryKeyword = (): void =>
  addTag(secondaryDraft, secondaryKeywords, 10, "二级关键词");
const removeRegion = (index: number): void => removeTag(regions, index);
const removeSecondaryKeyword = (index: number): void =>
  removeTag(secondaryKeywords, index);

const openGeneration = async (generationId: string): Promise<void> => {
  actionError.value = "";
  try {
    detailGeneration.value = await getKeywordGeneration(generationId);
  } catch (error) {
    actionError.value = errorMessage(error, "关键词任务载入失败");
  }
};

const followJob = async (
  jobId: string,
  generationId: string,
  options: { announce?: boolean } = {},
): Promise<void> => {
  if (followedJobId === jobId) return;
  followedJobId = jobId;
  const generation = ++pollGeneration;
  if (options.announce !== false) {
    notifyRequestInfo("关键词生成已开始", "系统会自动等待结果，无需手动刷新");
  }
  try {
    const job = await pollJobUntilTerminal(() => getJob(jobId), {
      intervalMs: STANDARD_JOB_POLLING_INTERVAL,
      timeoutMs: 5 * 60_000,
      timeoutMessage: "关键词生成超过 5 分钟仍未完成，请稍后重新发起",
      cancellationMessage: "关键词任务跟踪已取消",
      isCancelled: () => generation !== pollGeneration,
      onUpdate: (current) => {
        jobMessage.value = formatJobProgress(current);
      },
    });
    jobMessage.value = "";
    await workspaceQuery.refetch();
    if (job.status !== "succeeded") {
      throw new Error(job.error_message ?? "关键词生成任务未完成");
    }
    await openGeneration(generationId);
    notifyRequestSuccess(
      "关键词生成完成",
      "候选关键词已生成，请选择后确认保存",
    );
  } catch (error) {
    if (generation !== pollGeneration) return;
    jobMessage.value = "";
    actionError.value = errorMessage(error, "关键词生成失败");
    notifyRequestError("关键词生成未完成", actionError.value);
    await workspaceQuery.refetch();
  } finally {
    if (followedJobId === jobId) followedJobId = "";
  }
};

watch(
  generations,
  (items) => {
    const active = items.find(
      (item) => ["queued", "running"].includes(item.status) && item.job_id,
    );
    if (active?.job_id && active.job_id !== followedJobId) {
      void followJob(active.job_id, active.id, { announce: false });
    }
  },
  { immediate: true },
);

const generationMutation = useMutation({
  mutationFn: async () => {
    const currentProfile = profile.value;
    if (!currentProfile || !clientId.value) throw new Error("请先选择客户");
    if (!profileIsValid.value) {
      throw new Error("请完整填写主关键词、地区、关键词类型和生成数量");
    }
    const saved = await saveKeywordProfile(clientId.value, {
      version: currentProfile.version,
      primary_keyword: primaryKeyword.value.trim(),
      regions: regions.value,
      secondary_keywords: secondaryKeywords.value,
      keyword_types: selectedTypes.value,
    });
    const accepted = await createKeywordGeneration(
      clientId.value,
      { profile_version: saved.version, target_count: targetCount.value },
      crypto.randomUUID(),
    );
    await workspaceQuery.refetch();
    await followJob(accepted.job_id, accepted.generation_id);
  },
  onMutate: () => {
    actionError.value = "";
    jobMessage.value = "AI 正在组合地区、业务和用户意图…";
  },
  onError: (error: unknown) => {
    actionError.value = errorMessage(error, "关键词任务创建失败");
    jobMessage.value = "";
    notifyRequestError("无法生成关键词", actionError.value);
  },
});

const replaceCandidate = (updated: KeywordCandidateData): void => {
  if (!detailGeneration.value?.candidates) return;
  detailGeneration.value = {
    ...detailGeneration.value,
    candidates: detailGeneration.value.candidates.map((item) =>
      item.id === updated.id ? updated : item,
    ),
  };
};
const toggleCandidate = async (
  candidate: KeywordCandidateData,
): Promise<void> => {
  candidateBusy.value = true;
  actionError.value = "";
  try {
    replaceCandidate(
      await updateKeywordCandidate(candidate.id, {
        version: candidate.version,
        selected: !candidate.selected,
        active: true,
      }),
    );
  } catch (error) {
    actionError.value = errorMessage(error, "候选关键词更新失败");
  } finally {
    candidateBusy.value = false;
  }
};
const setAllCandidates = async (): Promise<void> => {
  const selected = !allCandidatesSelected.value;
  candidateBusy.value = true;
  actionError.value = "";
  try {
    const updated = await Promise.all(
      activeCandidates.value.map((candidate) =>
        updateKeywordCandidate(candidate.id, {
          version: candidate.version,
          selected,
          active: true,
        }),
      ),
    );
    updated.forEach(replaceCandidate);
  } catch (error) {
    actionError.value = errorMessage(error, "批量选择失败，请重试");
    if (detailGeneration.value) {
      await openGeneration(detailGeneration.value.id);
    }
  } finally {
    candidateBusy.value = false;
  }
};
const removeCandidate = async (
  candidate: KeywordCandidateData,
): Promise<void> => {
  candidateBusy.value = true;
  actionError.value = "";
  try {
    replaceCandidate(
      await updateKeywordCandidate(candidate.id, {
        version: candidate.version,
        selected: false,
        active: false,
      }),
    );
  } catch (error) {
    actionError.value = errorMessage(error, "候选关键词删除失败");
  } finally {
    candidateBusy.value = false;
  }
};

const confirmMutation = useMutation({
  mutationFn: async () => {
    const generation = detailGeneration.value;
    if (!generation) throw new Error("关键词任务不存在");
    if (!selectedCandidateIds.value.length)
      throw new Error("请至少选择一个关键词");
    return confirmKeywordGeneration(generation.id, {
      version: generation.version,
      candidate_ids: selectedCandidateIds.value,
    });
  },
  onSuccess: async () => {
    detailGeneration.value = null;
    await workspaceQuery.refetch();
    notifyRequestSuccess(
      "关键词已保存",
      "已进入正式关键词库，可用于批量生成文章",
    );
  },
  onError: (error: unknown) => {
    actionError.value = errorMessage(error, "关键词确认失败");
    notifyRequestError("关键词未保存", actionError.value);
  },
});

const deleteTask = async (): Promise<void> => {
  const target = deleteTaskTarget.value;
  if (!target) return;
  actionError.value = "";
  try {
    await archiveKeywordGeneration(target.id, target.version);
    deleteTaskTarget.value = null;
    if (detailGeneration.value?.id === target.id) detailGeneration.value = null;
    await workspaceQuery.refetch();
    notifyRequestSuccess("关键词任务已删除");
  } catch (error) {
    actionError.value = errorMessage(error, "任务删除失败");
  }
};

const deleteConfirmed = async (): Promise<void> => {
  const target = deleteKeywordTarget.value;
  if (!target) return;
  actionError.value = "";
  try {
    await updateStrategyItem(target.id, {
      version: target.version,
      selected: false,
      active: false,
    });
    deleteKeywordTarget.value = null;
    await workspaceQuery.refetch();
    notifyRequestSuccess("正式关键词已删除");
  } catch (error) {
    actionError.value = errorMessage(error, "正式关键词删除失败");
  }
};
</script>

<template>
  <AppShell>
    <main class="workspace keyword-page keyword-workspace">
      <header class="page-head page-head--action">
        <div>
          <p class="eyebrow">AI KEYWORD WORKSPACE · 关键词</p>
          <h1>关键词策略</h1>
          <p>
            先确认企业要覆盖的业务与地区，再由 AI
            生成真实用户可能提出的问题。只有确认后的关键词才会进入内容工作台。
          </p>
        </div>
      </header>

      <p v-if="jobMessage" class="task-banner" aria-live="polite">
        <span class="task-pulse" />{{ jobMessage }}
      </p>
      <p v-if="actionError" class="inline-error" role="alert">
        {{ actionError }}
      </p>

      <section v-if="!clientId" class="panel keyword-empty">
        <div>
          <h2>请先选择客户</h2>
          <p>关键词必须基于当前客户的企业知识库单独生成。</p>
        </div>
      </section>
      <section
        v-else-if="workspaceQuery.isPending.value"
        class="panel loading-panel"
        aria-busy="true"
      >
        <span class="loading-orbit" />
        <h2>正在读取关键词建议</h2>
        <p>AI 正在从企业资料中提炼主营业务、服务地区与经营项目…</p>
      </section>
      <section
        v-else-if="workspaceQuery.isError.value"
        class="panel error-panel"
        role="alert"
      >
        <h2>关键词工作台暂时无法载入</h2>
        <p>请检查服务后重试，系统不会混用其他客户的数据。</p>
        <button class="button primary" @click="workspaceQuery.refetch()">
          重新载入
        </button>
      </section>

      <template v-else-if="profile">
        <section class="panel keyword-config-panel">
          <header class="keyword-section-head">
            <div>
              <span class="section-step">01</span>
              <div>
                <h2>确认关键词生成范围</h2>
                <p>
                  蓝色建议来自企业知识库，可直接修改；保存后只影响后续新任务。
                </p>
              </div>
            </div>
            <span class="ai-suggestion-badge">
              {{ profile.inferred ? "AI 初始建议" : "已保存配置" }}
            </span>
          </header>

          <div class="keyword-config-grid">
            <label class="keyword-config-field keyword-config-field--primary">
              <span>主关键词 <small>建议只保留一个核心业务</small></span>
              <input
                v-model="primaryKeyword"
                maxlength="300"
                placeholder="例如：少儿美术培训"
              />
            </label>

            <div class="keyword-config-field">
              <span
                >建议地区 <small>{{ regions.length }}/5</small></span
              >
              <div class="editable-tag-box">
                <button
                  v-for="(region, index) in regions"
                  :key="region"
                  type="button"
                  class="editable-tag"
                  :aria-label="`删除地区${region}`"
                  @click="removeRegion(index)"
                >
                  {{ region }} <b aria-hidden="true">×</b>
                </button>
                <input
                  v-model="regionDraft"
                  :disabled="regions.length >= 5"
                  placeholder="输入地区后按回车"
                  @keydown.enter.prevent="addRegion"
                />
                <button
                  class="tag-add-button"
                  type="button"
                  :disabled="regions.length >= 5 || !regionDraft.trim()"
                  @click="addRegion"
                >
                  添加
                </button>
              </div>
              <small class="field-help">可覆盖行政区全称和用户常用简称。</small>
            </div>

            <div class="keyword-config-field">
              <span
                >二级关键词
                <small>{{ secondaryKeywords.length }}/10</small></span
              >
              <div class="editable-tag-box">
                <button
                  v-for="(keyword, index) in secondaryKeywords"
                  :key="keyword"
                  type="button"
                  class="editable-tag editable-tag--secondary"
                  :aria-label="`删除二级关键词${keyword}`"
                  @click="removeSecondaryKeyword(index)"
                >
                  {{ keyword }} <b aria-hidden="true">×</b>
                </button>
                <input
                  v-model="secondaryDraft"
                  :disabled="secondaryKeywords.length >= 10"
                  placeholder="例如：硬笔书法"
                  @keydown.enter.prevent="addSecondaryKeyword"
                />
                <button
                  class="tag-add-button"
                  type="button"
                  :disabled="
                    secondaryKeywords.length >= 10 || !secondaryDraft.trim()
                  "
                  @click="addSecondaryKeyword"
                >
                  添加
                </button>
              </div>
              <small class="field-help"
                >填写其他真实经营项目，不必把企业介绍整段放进来。</small
              >
            </div>
          </div>

          <div class="keyword-type-section">
            <div class="keyword-type-heading">
              <strong>本次覆盖的用户意图</strong>
              <small>可多选，至少选择 1 类</small>
            </div>
            <div class="keyword-type-grid">
              <label
                v-for="[value, label] in keywordTypes"
                :key="value"
                class="keyword-type-option"
                :class="{ selected: selectedTypes.includes(value) }"
              >
                <input v-model="selectedTypes" type="checkbox" :value="value" />
                <span>
                  <strong>{{ label }}</strong>
                  <small>{{ keywordTypeDescription[value] }}</small>
                </span>
                <i aria-hidden="true">✓</i>
              </label>
            </div>
          </div>

          <footer class="keyword-generate-bar">
            <div>
              <label>
                <span>期望生成数量</span>
                <input
                  v-model.number="targetCount"
                  type="number"
                  min="5"
                  max="50"
                />
              </label>
              <p>
                AI 建议 {{ profile.recommended_count }} 个；可填写 5–50
                个。质量过滤后实际数量可能略少。
              </p>
            </div>
            <button
              class="button primary keyword-generate-button"
              type="button"
              :disabled="!profileIsValid || generationMutation.isPending.value"
              @click="generationMutation.mutate()"
            >
              {{
                generationMutation.isPending.value
                  ? "AI 生成中…"
                  : "确认并生成关键词"
              }}
            </button>
          </footer>
        </section>

        <section class="panel keyword-task-panel">
          <header class="keyword-section-head">
            <div>
              <span class="section-step">02</span>
              <div>
                <h2>关键词生成任务</h2>
                <p>每次生成保留独立快照，可查看候选词后再决定是否保存。</p>
              </div>
            </div>
            <span>{{ generations.length }} 个任务</span>
          </header>
          <div v-if="generations.length" class="data-table-wrap">
            <table class="data-table keyword-task-table">
              <thead>
                <tr>
                  <th>主关键词</th>
                  <th>地区</th>
                  <th>二级关键词</th>
                  <th>关键词类型</th>
                  <th>状态</th>
                  <th>数量</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="task in generations" :key="task.id">
                  <td>
                    <strong>{{ task.primary_keyword }}</strong>
                  </td>
                  <td>{{ task.regions.join("、") }}</td>
                  <td>{{ task.secondary_keywords.join("、") || "—" }}</td>
                  <td>
                    <div class="compact-tags">
                      <span v-for="type in task.keyword_types" :key="type">
                        {{ keywordTypeLabel[type] }}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span class="task-status" :data-status="task.status">
                      {{ generationStatusLabel[task.status] }}
                    </span>
                    <small v-if="task.error_message">{{
                      task.error_message
                    }}</small>
                  </td>
                  <td>
                    <strong>{{ task.generated_count }}</strong>
                    <small>/ 期望 {{ task.target_count }}</small>
                  </td>
                  <td>{{ formatDateTime(task.created_at) }}</td>
                  <td>
                    <div class="table-actions">
                      <button
                        class="text-action primary"
                        type="button"
                        :disabled="['queued', 'running'].includes(task.status)"
                        @click="openGeneration(task.id)"
                      >
                        查看
                      </button>
                      <button
                        class="text-action danger"
                        type="button"
                        @click="deleteTaskTarget = task"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="keyword-task-empty">
            <strong>还没有生成任务</strong>
            <p>完成上方配置后，点击“确认并生成关键词”。</p>
          </div>
        </section>

        <section class="panel confirmed-keyword-panel">
          <header class="keyword-section-head">
            <div>
              <span class="section-step">03</span>
              <div>
                <h2>正式关键词库</h2>
                <p>
                  这里保存的是正式关键词；生成文章时可在内容工作台按任务自由选择。
                </p>
              </div>
            </div>
          </header>
          <div v-if="confirmedKeywords.length" class="confirmed-keyword-grid">
            <article v-for="keyword in confirmedKeywords" :key="keyword.id">
              <div class="confirmed-keyword-copy">
                <span>
                  <strong>{{ keyword.text }}</strong>
                  <small>
                    {{
                      keyword.keyword_type
                        ? keywordTypeLabel[keyword.keyword_type]
                        : "其他"
                    }}
                    · {{ keyword.main_keyword || "未设置主关键词" }}
                  </small>
                </span>
              </div>
              <button
                class="text-action danger"
                type="button"
                @click="deleteKeywordTarget = keyword"
              >
                删除
              </button>
            </article>
          </div>
          <div v-else class="keyword-task-empty">
            <strong>还没有正式关键词</strong>
            <p>打开一个已生成任务，选择候选关键词并确认保存。</p>
          </div>
        </section>
      </template>
    </main>
  </AppShell>

  <ModalDialog
    v-if="detailGeneration"
    title="查看本次生成的关键词"
    size="large"
    :close-disabled="confirmMutation.isPending.value || candidateBusy"
    @close="detailGeneration = null"
  >
    <div class="candidate-modal">
      <div class="candidate-summary">
        <div>
          <span>主关键词</span
          ><strong>{{ detailGeneration.primary_keyword }}</strong>
        </div>
        <div>
          <span>期望数量</span
          ><strong>{{ detailGeneration.target_count }}</strong>
        </div>
        <div>
          <span>实际生成</span
          ><strong>{{ detailGeneration.generated_count }}</strong>
        </div>
        <div>
          <span>已选择</span><strong>{{ selectedCandidateIds.length }}</strong>
        </div>
      </div>
      <div
        v-if="detailGeneration.status === 'failed'"
        class="inline-error"
        role="alert"
      >
        {{ detailGeneration.error_message || "本次生成失败，请重新创建任务" }}
      </div>
      <template v-else>
        <div class="candidate-toolbar">
          <label>
            <input
              type="checkbox"
              :checked="allCandidatesSelected"
              :disabled="
                candidateBusy ||
                detailGeneration.status !== 'awaiting_confirmation'
              "
              @change="setAllCandidates"
            />
            全选本页
          </label>
          <span>基础去重已完成；标题将在生成文章时再次进行严格去重。</span>
        </div>
        <div class="candidate-list">
          <article v-for="candidate in activeCandidates" :key="candidate.id">
            <label>
              <input
                type="checkbox"
                :checked="candidate.selected"
                :disabled="
                  candidateBusy ||
                  detailGeneration.status !== 'awaiting_confirmation'
                "
                @change="toggleCandidate(candidate)"
              />
              <span>
                <strong>{{ candidate.text }}</strong>
                <small>
                  {{ keywordTypeLabel[candidate.keyword_type] }} ·
                  {{ candidate.user_intent }}
                </small>
              </span>
            </label>
            <button
              v-if="detailGeneration.status === 'awaiting_confirmation'"
              class="text-action danger"
              type="button"
              :disabled="candidateBusy"
              @click="removeCandidate(candidate)"
            >
              删除
            </button>
          </article>
        </div>
      </template>
      <footer class="modal-actions">
        <button
          class="button secondary"
          type="button"
          :disabled="confirmMutation.isPending.value || candidateBusy"
          @click="detailGeneration = null"
        >
          关闭
        </button>
        <button
          v-if="detailGeneration.status === 'awaiting_confirmation'"
          class="button primary"
          type="button"
          :disabled="
            selectedCandidateIds.length === 0 ||
            confirmMutation.isPending.value ||
            candidateBusy
          "
          @click="confirmMutation.mutate()"
        >
          {{
            confirmMutation.isPending.value
              ? "保存中…"
              : `确认保存 ${selectedCandidateIds.length} 个关键词`
          }}
        </button>
      </footer>
    </div>
  </ModalDialog>

  <ModalDialog
    v-if="deleteTaskTarget"
    title="删除关键词任务"
    size="small"
    @close="deleteTaskTarget = null"
  >
    <div class="confirm-dialog-copy">
      <p>确定删除“{{ deleteTaskTarget.primary_keyword }}”的本次生成记录吗？</p>
      <small
        >已确认进入正式关键词库的内容不会被删除；历史去重记录仍会保留。</small
      >
    </div>
    <footer class="modal-actions">
      <button
        class="button secondary"
        type="button"
        @click="deleteTaskTarget = null"
      >
        取消
      </button>
      <button class="button danger" type="button" @click="deleteTask">
        确认删除
      </button>
    </footer>
  </ModalDialog>

  <ModalDialog
    v-if="deleteKeywordTarget"
    title="删除正式关键词"
    size="small"
    @close="deleteKeywordTarget = null"
  >
    <div class="confirm-dialog-copy">
      <p>确定删除“{{ deleteKeywordTarget.text }}”吗？</p>
      <small
        >该关键词以后不会再用于生成新文章，已经生成的文章不会受影响。</small
      >
    </div>
    <footer class="modal-actions">
      <button
        class="button secondary"
        type="button"
        @click="deleteKeywordTarget = null"
      >
        取消
      </button>
      <button class="button danger" type="button" @click="deleteConfirmed">
        确认删除
      </button>
    </footer>
  </ModalDialog>
</template>

<style scoped>
.keyword-workspace {
  --keyword-blue: #2f6fec;
  --keyword-blue-soft: #eff5ff;
  --keyword-line: #dfe8f4;
}

.keyword-config-panel,
.keyword-task-panel,
.confirmed-keyword-panel {
  overflow: hidden;
  margin-bottom: 18px;
  border-color: var(--keyword-line);
  box-shadow: 0 14px 38px rgb(38 76 118 / 8%);
}

.keyword-section-head {
  display: flex;
  min-height: 82px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--keyword-line);
  background: linear-gradient(100deg, #fff 0%, #f8fbff 100%);
}

.keyword-section-head > div {
  display: flex;
  align-items: center;
  gap: 13px;
}

.keyword-section-head h2,
.keyword-section-head p {
  margin: 0;
}

.keyword-section-head h2 {
  color: #163d62;
  font-size: 19px;
}

.keyword-section-head p,
.keyword-section-head > span {
  margin-top: 4px;
  color: #718093;
  font-size: 12px;
}

.section-step {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  place-items: center;
  border-radius: 11px;
  background: linear-gradient(145deg, #e9f1ff, #f7faff);
  color: var(--keyword-blue);
  font-size: 13px;
  font-weight: 900;
}

.ai-suggestion-badge {
  padding: 6px 11px;
  border: 1px solid #cfe0ff;
  border-radius: 999px;
  background: var(--keyword-blue-soft);
  color: #285dbd !important;
  font-weight: 750;
}

.keyword-config-grid {
  display: grid;
  padding: 22px;
  grid-template-columns: minmax(240px, 0.72fr) minmax(320px, 1.28fr);
  gap: 20px;
}

.keyword-config-field {
  display: grid;
  align-content: start;
  gap: 8px;
}

.keyword-config-field--primary {
  grid-row: span 2;
}

.keyword-config-field > span,
.keyword-type-heading strong {
  color: #26445f;
  font-size: 13px;
  font-weight: 800;
}

.keyword-config-field > span small,
.keyword-type-heading small {
  margin-left: 6px;
  color: #8b98a7;
  font-weight: 600;
}

.keyword-config-field > input {
  min-height: 52px;
  padding: 0 15px;
  border: 1px solid #cddaea;
  border-radius: 11px;
  background: #fbfdff;
  color: #183b5c;
  font-size: 17px;
  font-weight: 800;
  outline: none;
}

.keyword-config-field > input:focus,
.editable-tag-box:focus-within {
  border-color: #78a4f5;
  box-shadow: 0 0 0 3px rgb(47 111 236 / 10%);
}

.editable-tag-box {
  display: flex;
  min-height: 52px;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  padding: 7px;
  border: 1px solid #cddaea;
  border-radius: 11px;
  background: #fbfdff;
}

.editable-tag-box input {
  min-width: 135px;
  flex: 1 1 150px;
  height: 34px;
  padding: 0 6px;
  border: 0;
  outline: none;
  background: transparent;
  color: #29445e;
}

.editable-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border: 1px solid #cfe0ff;
  border-radius: 8px;
  background: #edf4ff;
  color: #285aa9;
  font-size: 12px;
  font-weight: 750;
}

.editable-tag--secondary {
  border-color: #d9d2ff;
  background: #f5f1ff;
  color: #6550b5;
}

.editable-tag b {
  font-size: 15px;
  line-height: 1;
}

.tag-add-button {
  height: 34px;
  padding: 0 11px;
  border: 0;
  border-radius: 8px;
  background: #e8f0ff;
  color: #2d64c4;
  font-size: 12px;
  font-weight: 800;
}

.field-help {
  color: #8a98a6;
  font-size: 11px;
}

.keyword-type-section {
  padding: 0 22px 22px;
}

.keyword-type-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 11px;
}

.keyword-type-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.keyword-type-option {
  position: relative;
  display: flex;
  min-height: 78px;
  align-items: center;
  gap: 11px;
  padding: 13px;
  border: 1px solid #dce5ef;
  border-radius: 11px;
  background: #fff;
  cursor: pointer;
}

.keyword-type-option:hover,
.keyword-type-option.selected {
  border-color: #9abcf8;
  background: #f5f8ff;
}

.keyword-type-option input {
  width: 17px;
  height: 17px;
  accent-color: var(--keyword-blue);
}

.keyword-type-option span {
  display: grid;
  gap: 4px;
}

.keyword-type-option strong {
  color: #24435f;
  font-size: 13px;
}

.keyword-type-option small {
  color: #7f8d9b;
  font-size: 11px;
  line-height: 1.45;
}

.keyword-type-option i {
  position: absolute;
  top: 8px;
  right: 9px;
  color: transparent;
  font-style: normal;
  font-size: 12px;
}

.keyword-type-option.selected i {
  color: var(--keyword-blue);
}

.keyword-generate-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 22px;
  padding: 17px 22px;
  border-top: 1px solid var(--keyword-line);
  background: #f8fbff;
}

.keyword-generate-bar > div,
.keyword-generate-bar label {
  display: flex;
  align-items: center;
  gap: 10px;
}

.keyword-generate-bar label span {
  color: #29455e;
  font-size: 13px;
  font-weight: 800;
}

.keyword-generate-bar input {
  width: 84px;
  height: 38px;
  padding: 0 10px;
  border: 1px solid #cbd9e8;
  border-radius: 8px;
  background: #fff;
  color: #21405e;
  font-weight: 800;
}

.keyword-generate-bar p {
  margin: 0;
  color: #7f8c99;
  font-size: 11px;
}

.keyword-generate-button {
  min-width: 190px;
  box-shadow: 0 9px 22px rgb(47 111 236 / 20%);
}

.keyword-task-table {
  min-width: 1120px;
}

.keyword-task-table td {
  max-width: 250px;
  color: #516274;
  line-height: 1.5;
}

.keyword-task-table td:first-child strong {
  color: #193f65;
}

.compact-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.compact-tags span {
  padding: 3px 6px;
  border-radius: 6px;
  background: #eff4fb;
  color: #527197;
  font-size: 10px;
}

.task-status {
  display: inline-flex;
  padding: 5px 9px;
  border-radius: 999px;
  background: #eef2f5;
  color: #63717d;
  font-size: 11px;
  font-weight: 800;
}

.task-status[data-status="running"],
.task-status[data-status="queued"] {
  background: #e9f1ff;
  color: #2961be;
}

.task-status[data-status="awaiting_confirmation"] {
  background: #fff1d9;
  color: #92610d;
}

.task-status[data-status="confirmed"] {
  background: #e4f8ef;
  color: #087453;
}

.task-status[data-status="failed"] {
  background: #fdebe9;
  color: #b14a42;
}

.keyword-task-empty {
  padding: 42px 22px;
  text-align: center;
}

.keyword-task-empty strong {
  color: #34526e;
}

.keyword-task-empty p {
  margin: 7px 0 0;
  color: #8895a1;
  font-size: 12px;
}

.confirmed-keyword-grid {
  display: grid;
  padding: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.confirmed-keyword-grid article {
  display: flex;
  min-height: 70px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 14px;
  border: 1px solid #e0e8f0;
  border-radius: 11px;
  background: #fff;
}

.confirmed-keyword-grid article.selected {
  border-color: #bed2fa;
  background: #f7faff;
}

.confirmed-keyword-grid label,
.confirmed-keyword-copy,
.candidate-list label {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 11px;
  cursor: pointer;
}

.confirmed-keyword-grid input,
.candidate-list input,
.candidate-toolbar input {
  width: 17px;
  height: 17px;
  flex: 0 0 17px;
  accent-color: var(--keyword-blue);
}

.confirmed-keyword-grid label span,
.confirmed-keyword-copy span,
.candidate-list label span {
  display: grid;
  gap: 5px;
}

.confirmed-keyword-grid strong,
.candidate-list strong {
  color: #234461;
  font-size: 13px;
}

.confirmed-keyword-grid small,
.candidate-list small {
  color: #83909c;
  font-size: 11px;
}

.candidate-modal {
  display: grid;
  gap: 16px;
}

.candidate-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 9px;
}

.candidate-summary > div {
  display: grid;
  gap: 5px;
  padding: 12px 14px;
  border: 1px solid #e0e8f2;
  border-radius: 10px;
  background: #f8fbff;
}

.candidate-summary span {
  color: #8492a0;
  font-size: 11px;
}

.candidate-summary strong {
  color: #244865;
  font-size: 18px;
}

.candidate-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 9px;
  background: #f3f7fc;
}

.candidate-toolbar label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #36536e;
  font-size: 12px;
  font-weight: 800;
}

.candidate-toolbar span {
  color: #82909e;
  font-size: 11px;
}

.candidate-list {
  display: grid;
  max-height: 52vh;
  overflow-y: auto;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding-right: 4px;
}

.candidate-list article {
  display: flex;
  min-height: 67px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid #e1e9f1;
  border-radius: 10px;
  background: #fff;
}

.confirm-dialog-copy p {
  margin: 0;
  color: #29445d;
  font-weight: 750;
  line-height: 1.65;
}

.confirm-dialog-copy small {
  display: block;
  margin-top: 8px;
  color: #84909b;
  line-height: 1.6;
}

@media (max-width: 1180px) {
  .keyword-type-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .confirmed-keyword-grid,
  .candidate-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .keyword-config-grid {
    grid-template-columns: 1fr;
  }

  .keyword-config-field--primary {
    grid-row: auto;
  }

  .keyword-type-grid,
  .candidate-summary {
    grid-template-columns: 1fr;
  }

  .keyword-generate-bar,
  .keyword-generate-bar > div,
  .candidate-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
