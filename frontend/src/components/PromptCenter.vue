<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type {
  ContactPolicy,
  PromptCategory,
  PromptTemplateData,
  PromptTemplateVersionData,
} from "../api/dto";
import {
  getPromptTemplates,
  getPromptTemplateVersions,
  restorePromptTemplate,
  updatePromptTemplate,
} from "../api/prompts";

type PromptSection =
  "content_form" | "keyword_strategy" | "channel_adapter" | "foundation";

const sections: { value: PromptSection; label: string; hint: string }[] = [
  { value: "content_form", label: "文章形式", hint: "不同文章使用不同结构" },
  { value: "keyword_strategy", label: "关键词策略", hint: "控制问题覆盖范围" },
  { value: "channel_adapter", label: "渠道规则", hint: "控制表达与联系方式" },
  { value: "foundation", label: "通用规则", hint: "事实边界与自然表达" },
];
const contactPolicyLabels: Record<ContactPolicy, string> = {
  allow: "允许已核验联系方式",
  official_only: "仅保留官方主页入口",
  omit: "删除手机号、微信与外链",
  manual_review: "默认隐藏，发布前复核",
};

const templates = ref<PromptTemplateData[]>([]);
const availableVariables = ref<string[]>([]);
const guardrailSummary = ref("");
const activeSection = ref<PromptSection>("content_form");
const selectedId = ref("");
const draftText = ref("");
const draftActive = ref(true);
const draftContactPolicy = ref<ContactPolicy>("manual_review");
const changeNote = ref("运营配置更新");
const loading = ref(true);
const saving = ref(false);
const restoring = ref(false);
const error = ref("");
const message = ref("");
const history = ref<PromptTemplateVersionData[]>([]);
const historyLoading = ref(false);

const filteredTemplates = computed(() =>
  templates.value.filter((item) =>
    activeSection.value === "foundation"
      ? item.category === "guardrail" || item.category === "base"
      : item.category === activeSection.value,
  ),
);
const selectedTemplate = computed(() =>
  templates.value.find((item) => item.id === selectedId.value),
);
const selectedSection = computed(() =>
  sections.find((item) => item.value === activeSection.value),
);

const syncDraft = (template: PromptTemplateData | undefined): void => {
  if (!template) return;
  draftText.value = template.template_text;
  draftActive.value = template.active;
  draftContactPolicy.value = template.contact_policy ?? "manual_review";
  changeNote.value = "运营配置更新";
};
watch(selectedTemplate, syncDraft, { immediate: true });
watch(activeSection, () => {
  selectedId.value = filteredTemplates.value[0]?.id ?? "";
  history.value = [];
});

const load = async (): Promise<void> => {
  loading.value = true;
  error.value = "";
  try {
    const result = await getPromptTemplates();
    templates.value = result.items;
    availableVariables.value = result.available_variables;
    guardrailSummary.value = result.guardrails.summary;
    selectedId.value = filteredTemplates.value[0]?.id ?? "";
  } catch (reason) {
    error.value =
      reason instanceof Error ? reason.message : "提示词配置载入失败";
  } finally {
    loading.value = false;
  }
};
const replaceTemplate = (updated: PromptTemplateData): void => {
  templates.value = templates.value.map((item) =>
    item.id === updated.id ? updated : item,
  );
  syncDraft(updated);
};
const save = async (): Promise<void> => {
  const template = selectedTemplate.value;
  if (!template?.editable || !draftText.value.trim()) return;
  saving.value = true;
  error.value = "";
  message.value = "";
  try {
    const updated = await updatePromptTemplate(template.id, {
      version: template.version,
      template_text: draftText.value.trim(),
      active: draftActive.value,
      contact_policy:
        template.category === "channel_adapter"
          ? draftContactPolicy.value
          : undefined,
      change_note: changeNote.value.trim() || "运营配置更新",
    });
    replaceTemplate(updated);
    message.value = `${updated.name}已保存为 v${updated.current_version}，只影响后续新任务`;
    await loadHistory();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "提示词保存失败";
  } finally {
    saving.value = false;
  }
};
const restore = async (): Promise<void> => {
  const template = selectedTemplate.value;
  if (
    !template?.editable ||
    !window.confirm(`确定将“${template.name}”恢复为系统默认提示词吗？`)
  )
    return;
  restoring.value = true;
  error.value = "";
  message.value = "";
  try {
    const updated = await restorePromptTemplate(template.id, template.version);
    replaceTemplate(updated);
    message.value = `${updated.name}已恢复默认，并保留历史版本`;
    await loadHistory();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "恢复默认失败";
  } finally {
    restoring.value = false;
  }
};
const loadHistory = async (): Promise<void> => {
  const template = selectedTemplate.value;
  if (!template) return;
  historyLoading.value = true;
  try {
    history.value = (await getPromptTemplateVersions(template.id)).items;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "版本历史载入失败";
  } finally {
    historyLoading.value = false;
  }
};
const insertVariable = (variable: string): void => {
  if (!selectedTemplate.value?.editable) return;
  const token = `{{${variable}}}`;
  draftText.value = `${draftText.value.trimEnd()}${draftText.value ? "\n" : ""}${token}`;
};
const categoryLabel = (category: PromptCategory): string =>
  ({
    guardrail: "系统保护",
    base: "通用写作",
    content_form: "文章形式",
    keyword_strategy: "关键词策略",
    channel_adapter: "渠道适配",
  })[category];

onMounted(load);
</script>

<template>
  <section class="prompt-center-section">
    <div class="section-title-row">
      <div>
        <span class="section-index">03</span>
        <h2>提示词与渠道合规</h2>
        <p>
          内容形式、关键词策略和渠道规则可由运营维护；每次修改都会新增版本，不改写历史文章。
        </p>
      </div>
      <span class="security-seal">系统保护层只读</span>
    </div>

    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <p v-if="message" class="inline-success" role="status">{{ message }}</p>

    <div v-if="loading" class="panel prompt-center-loading">
      正在载入提示词配置…
    </div>
    <div v-else class="prompt-center">
      <aside class="prompt-library">
        <nav aria-label="提示词分类">
          <button
            v-for="section in sections"
            :key="section.value"
            type="button"
            :class="{ active: activeSection === section.value }"
            @click="activeSection = section.value"
          >
            <strong>{{ section.label }}</strong>
            <span>{{ section.hint }}</span>
          </button>
        </nav>
        <div class="prompt-template-list">
          <button
            v-for="template in filteredTemplates"
            :key="template.id"
            type="button"
            :class="{ active: selectedId === template.id }"
            @click="
              selectedId = template.id;
              history = [];
            "
          >
            <span>
              <strong>{{ template.name }}</strong>
              <small>{{ categoryLabel(template.category) }}</small>
            </span>
            <em>v{{ template.current_version }}</em>
          </button>
        </div>
      </aside>

      <article v-if="selectedTemplate" class="prompt-editor-card">
        <header>
          <div>
            <div class="prompt-editor-title">
              <h3>{{ selectedTemplate.name }}</h3>
              <span v-if="!selectedTemplate.editable">系统只读</span>
              <span v-else-if="selectedTemplate.active">使用中</span>
              <span v-else class="muted">已停用</span>
            </div>
            <p>{{ selectedTemplate.description }}</p>
          </div>
          <div class="prompt-version-mark">
            <span>当前版本</span>
            <strong>v{{ selectedTemplate.current_version }}</strong>
          </div>
        </header>

        <div v-if="!selectedTemplate.editable" class="guardrail-banner">
          <strong>为什么不能编辑</strong>
          <span>{{ guardrailSummary }}</span>
        </div>

        <label
          v-if="selectedTemplate.category === 'channel_adapter'"
          class="field prompt-policy-field"
        >
          <span>联系方式处理规则</span>
          <select
            v-model="draftContactPolicy"
            :disabled="!selectedTemplate.editable"
          >
            <option
              v-for="(label, value) in contactPolicyLabels"
              :key="value"
              :value="value"
            >
              {{ label }}
            </option>
          </select>
        </label>

        <label class="field prompt-text-field">
          <span>提示词内容</span>
          <textarea
            v-model="draftText"
            rows="13"
            :readonly="!selectedTemplate.editable"
          />
        </label>

        <div
          v-if="selectedTemplate.editable && availableVariables.length"
          class="prompt-variables"
        >
          <span>插入动态变量</span>
          <button
            v-for="variable in availableVariables"
            :key="variable"
            type="button"
            @click="insertVariable(variable)"
          >
            {{ variable }}
          </button>
        </div>

        <label v-if="selectedTemplate.editable" class="field change-note-field">
          <span>本次修改说明</span>
          <input
            v-model="changeNote"
            maxlength="300"
            placeholder="例如：调整选择指南的文章结构"
          />
        </label>

        <footer class="prompt-editor-actions">
          <label v-if="selectedTemplate.editable" class="engine-switch">
            <input v-model="draftActive" type="checkbox" />
            <span />
            启用此模板
          </label>
          <div>
            <button
              class="button secondary"
              type="button"
              :disabled="historyLoading"
              @click="loadHistory"
            >
              {{ historyLoading ? "读取中…" : "查看版本" }}
            </button>
            <button
              v-if="selectedTemplate.editable"
              class="button secondary"
              type="button"
              :disabled="restoring || saving"
              @click="restore"
            >
              {{ restoring ? "恢复中…" : "恢复默认" }}
            </button>
            <button
              v-if="selectedTemplate.editable"
              class="button primary"
              type="button"
              :disabled="saving || restoring || draftText.trim().length < 2"
              @click="save"
            >
              {{ saving ? "保存中…" : "保存新版本" }}
            </button>
          </div>
        </footer>

        <div v-if="history.length" class="prompt-history">
          <h4>版本历史</h4>
          <ol>
            <li v-for="version in history.slice(0, 8)" :key="version.id">
              <strong>v{{ version.version_number }}</strong>
              <span>{{ version.change_note }}</span>
              <time>{{
                new Intl.DateTimeFormat("zh-CN", {
                  month: "2-digit",
                  day: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(version.created_at))
              }}</time>
            </li>
          </ol>
        </div>
      </article>
      <article v-else class="panel prompt-empty">
        <strong>{{ selectedSection?.label }}暂无模板</strong>
        <span>请刷新页面或检查服务端初始化状态。</span>
      </article>
    </div>
  </section>
</template>
