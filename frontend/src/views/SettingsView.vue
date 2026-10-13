<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type {
  ProviderName,
  ProviderSettingData,
  SettingsData,
} from "../api/dto";
import { ApiError } from "../api/http";
import {
  getSettings,
  testProvider,
  updateProvider,
  updateRuntime,
} from "../api/settings";
import AppShell from "../components/AppShell.vue";
import PromptCenter from "../components/PromptCenter.vue";

interface ProviderDraft {
  enabled: boolean;
  baseUrl: string;
  workspaceId: string;
  writerModel: string;
  reviewerModel: string;
  fallbackModel: string;
  dailyBudgetYuan: string;
  timeoutSeconds: string;
  apiKey: string;
}

const settings = ref<SettingsData | null>(null);
const loading = ref(true);
const error = ref("");
const successMessage = ref("");
const savingProvider = ref<ProviderName | null>(null);
const testingProvider = ref<ProviderName | null>(null);
const savingRuntime = ref(false);
const monthlyBudgetYuan = ref("300");
const drafts = reactive<Partial<Record<ProviderName, ProviderDraft>>>({});

const providerOrder: ProviderName[] = ["deepseek", "qwen", "doubao", "wenxin"];
const providerNames: Record<ProviderName, string> = {
  deepseek: "DeepSeek",
  doubao: "豆包",
  wenxin: "文心一言",
  yuanbao: "腾讯元宝",
  qwen: "通义千问",
  kimi: "Kimi",
};
const providerRoles: Record<ProviderName, string> = {
  deepseek: "文章主写 · GEO 自动检测",
  doubao: "GEO 自动检测 · 火山方舟 API",
  wenxin: "GEO 自动检测 · 百度千帆 API",
  yuanbao: "GEO 自动检测 · 腾讯模型 API",
  qwen: "生成备用 · GEO 自动检测",
  kimi: "GEO 自动检测 · Moonshot API",
};
const providerMarks: Record<ProviderName, string> = {
  deepseek: "D",
  doubao: "豆",
  wenxin: "文",
  yuanbao: "元",
  qwen: "Q",
  kimi: "K",
};
const providerName = (provider: ProviderName): string =>
  providerNames[provider];
const providerRole = (provider: ProviderName): string =>
  providerRoles[provider];
const providerMark = (provider: ProviderName): string =>
  providerMarks[provider];
const isDiagnosticOnlyProvider = (provider: ProviderName): boolean =>
  ["doubao", "wenxin", "yuanbao", "kimi"].includes(provider);
const formatTestedAt = (value: string | null): string => {
  if (!value) return "尚未验证";
  return `验证于 ${new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))}`;
};
const statusText = (provider: ProviderSettingData): string => {
  if (!provider.enabled) return "已停用";
  if (!provider.secret_configured) return "等待配置";
  if (provider.last_test_status === "success") return "连接已验证";
  if (provider.last_test_status === "failed") return "最近测试失败";
  return "密钥已保存，待测试";
};
const statusTone = (provider: ProviderSettingData): string => {
  if (!provider.enabled) return "pending";
  if (!provider.secret_configured) return "pending";
  if (provider.last_test_status === "success") return "success";
  if (provider.last_test_status === "failed") return "failed";
  return "ready";
};
const availableCount = computed(
  () =>
    settings.value?.providers.filter(
      (item) =>
        item.enabled &&
        item.secret_configured &&
        item.last_test_status === "success",
    ).length ?? 0,
);

const initializeDraft = (provider: ProviderSettingData): void => {
  drafts[provider.provider] = {
    enabled: provider.enabled,
    baseUrl: provider.base_url,
    workspaceId: provider.workspace_id ?? "",
    writerModel: provider.writer_model ?? "",
    reviewerModel: provider.reviewer_model ?? "",
    fallbackModel: provider.fallback_model ?? "",
    dailyBudgetYuan: String(provider.daily_budget_cny_fen / 100),
    timeoutSeconds: String(provider.timeout_seconds),
    apiKey: "",
  };
};
const load = async (): Promise<void> => {
  loading.value = true;
  error.value = "";
  try {
    settings.value = await getSettings();
    settings.value.providers.forEach(initializeDraft);
    monthlyBudgetYuan.value = String(
      settings.value.runtime.default_client_monthly_budget_cny_fen / 100,
    );
  } catch (reason: unknown) {
    error.value =
      reason instanceof Error ? reason.message : "系统设置加载失败，请稍后重试";
  } finally {
    loading.value = false;
  }
};
const reportError = (reason: unknown): void => {
  error.value =
    reason instanceof ApiError || reason instanceof Error
      ? reason.message
      : "操作失败，请稍后重试";
};
const isVersionConflict = (reason: unknown): boolean =>
  reason instanceof ApiError && reason.status === 409;
const persistProvider = async (
  provider: ProviderSettingData,
): Promise<ProviderSettingData> => {
  const draft = drafts[provider.provider];
  if (!draft) throw new Error("模型配置尚未载入");
  const updated = await updateProvider(provider.provider, {
    version: provider.version,
    enabled: draft.enabled,
    base_url: draft.baseUrl,
    workspace_id: draft.workspaceId.trim() || null,
    writer_model: draft.writerModel.trim() || null,
    reviewer_model: draft.reviewerModel.trim() || null,
    fallback_model: draft.fallbackModel.trim() || null,
    daily_budget_cny_fen: Math.round(
      Number(draft.dailyBudgetYuan || "0") * 100,
    ),
    timeout_seconds: Number(draft.timeoutSeconds),
    api_key: draft.apiKey.trim() || null,
  });
  if (settings.value)
    settings.value.providers = settings.value.providers.map((item) =>
      item.provider === updated.provider ? updated : item,
    );
  initializeDraft(updated);
  return updated;
};
const saveProvider = async (provider: ProviderSettingData): Promise<void> => {
  const draft = drafts[provider.provider];
  if (!draft) return;
  error.value = "";
  successMessage.value = "";
  savingProvider.value = provider.provider;
  try {
    const updated = await persistProvider(provider);
    successMessage.value = `${providerName(updated.provider)} 配置已安全保存`;
  } catch (reason: unknown) {
    if (isVersionConflict(reason)) await load();
    reportError(reason);
  } finally {
    draft.apiKey = "";
    savingProvider.value = null;
  }
};
const runProviderTest = async (
  provider: ProviderSettingData,
): Promise<void> => {
  const draft = drafts[provider.provider];
  if (!draft) return;
  error.value = "";
  successMessage.value = "";
  testingProvider.value = provider.provider;
  let persisted = false;
  try {
    draft.enabled = true;
    const updated = await persistProvider(provider);
    persisted = true;
    const result = await testProvider(updated.provider);
    successMessage.value = `${providerName(provider.provider)} 已验证：${result.model} · ${result.latency_ms}ms${
      result.budget_warning ? " · 今日预算已达到 80%" : ""
    }`;
    await load();
  } catch (reason: unknown) {
    if (persisted || isVersionConflict(reason)) await load();
    reportError(reason);
  } finally {
    draft.apiKey = "";
    testingProvider.value = null;
  }
};
const saveRuntime = async (): Promise<void> => {
  if (!settings.value) return;
  error.value = "";
  successMessage.value = "";
  savingRuntime.value = true;
  try {
    settings.value.runtime = await updateRuntime(
      settings.value.runtime.version,
      Math.round(Number(monthlyBudgetYuan.value || "0") * 100),
    );
    successMessage.value = "默认客户月度预算已更新";
  } catch (reason: unknown) {
    reportError(reason);
  } finally {
    savingRuntime.value = false;
  }
};
onMounted(load);
</script>

<template>
  <AppShell>
    <main class="workspace settings-page settings-command-center">
      <header class="settings-hero">
        <div>
          <p class="eyebrow">P08 · 模型与运行控制</p>
          <h1>AI 引擎控制台</h1>
          <p>
            DeepSeek 负责文章主写，通义千问作为生成备用；GEO 诊断固定检测
            DeepSeek、通义千问、豆包和文心一言。
          </p>
        </div>
        <div class="settings-score">
          <span>真实可用引擎</span>
          <strong>{{ availableCount }}<small>/ 4</small></strong>
          <em>{{
            availableCount === 4 ? "四平台连接已验证" : "部分平台等待配置"
          }}</em>
        </div>
      </header>

      <div v-if="error" class="settings-alert error" role="alert">
        <span>!</span>
        <div>
          <strong>操作未完成</strong>
          <p>{{ error }}</p>
        </div>
        <button aria-label="关闭错误提示" @click="error = ''">×</button>
      </div>
      <div v-if="successMessage" class="settings-alert success" role="status">
        <span>✓</span><strong>{{ successMessage }}</strong>
      </div>

      <section v-if="loading" class="panel settings-loading">
        正在读取服务端配置…
      </section>
      <template v-else-if="settings">
        <section class="provider-section">
          <div class="section-title-row">
            <div>
              <span class="section-index">01</span>
              <h2>内容模型与四平台检测连接</h2>
              <p>
                密钥提交后立即从输入框清除，浏览器不保存，也不会再次读取明文。
              </p>
            </div>
            <span class="security-seal">服务端加密存储</span>
          </div>

          <div class="provider-cards">
            <article
              v-for="providerNameKey in providerOrder"
              :key="providerNameKey"
              class="provider-card"
              :class="`provider-${providerNameKey}`"
            >
              <template
                v-if="
                  settings.providers.find(
                    (item) => item.provider === providerNameKey,
                  )
                "
              >
                <div
                  v-for="provider in [
                    settings.providers.find(
                      (item) => item.provider === providerNameKey,
                    )!,
                  ]"
                  :key="provider.provider"
                  class="provider-card-inner"
                >
                  <header>
                    <span class="provider-logo">{{
                      providerMark(provider.provider)
                    }}</span>
                    <div>
                      <p>{{ providerRole(provider.provider) }}</p>
                      <h3>{{ providerName(provider.provider) }}</h3>
                    </div>
                    <div class="provider-connection-status">
                      <span
                        class="connection-pill"
                        :data-tone="statusTone(provider)"
                      >
                        <i></i>{{ statusText(provider) }}
                      </span>
                      <small>{{
                        formatTestedAt(provider.last_tested_at)
                      }}</small>
                    </div>
                  </header>

                  <div class="model-route">
                    <div v-if="provider.provider === 'qwen'">
                      <span>备用生成模型</span>
                      <strong>{{ provider.writer_model }}</strong>
                      <small>同时用于通义千问 GEO 自动检测</small>
                    </div>
                    <div
                      v-else-if="isDiagnosticOnlyProvider(provider.provider)"
                    >
                      <span>自动检测模型 / 接入点</span>
                      <strong>{{
                        provider.writer_model || "等待填写模型或接入点 ID"
                      }}</strong>
                      <small>只参与 GEO 诊断，不参与文章生成</small>
                    </div>
                    <template v-else>
                      <div>
                        <span>默认主写模型</span>
                        <strong>{{ provider.reviewer_model }}</strong>
                        <small>负责内容提纲与正文生成</small>
                      </div>
                      <b>→</b>
                      <div>
                        <span>同厂备用模型</span>
                        <strong>{{ provider.fallback_model }}</strong>
                        <small>保留配置，不参与默认生成链路</small>
                      </div>
                    </template>
                  </div>

                  <div class="provider-form">
                    <label
                      v-if="isDiagnosticOnlyProvider(provider.provider)"
                      class="wide-field"
                    >
                      <span>检测模型 / 接入点 ID</span>
                      <input
                        v-model="drafts[provider.provider]!.writerModel"
                        autocomplete="off"
                        :placeholder="
                          provider.provider === 'doubao'
                            ? '填写火山方舟推理接入点 ID'
                            : '填写供应商支持的模型名称'
                        "
                      />
                    </label>
                    <label class="wide-field">
                      <span>API 地址</span>
                      <input
                        v-model="drafts[provider.provider]!.baseUrl"
                        type="url"
                      />
                    </label>
                    <label
                      v-if="provider.provider === 'qwen'"
                      class="wide-field"
                    >
                      <span>北京地域 Workspace ID <em>可选</em></span>
                      <input
                        v-model="drafts[provider.provider]!.workspaceId"
                        autocomplete="off"
                        placeholder="留空则使用账号默认空间"
                      />
                    </label>
                    <label class="wide-field secret-field">
                      <span>
                        API 密钥
                        <em v-if="provider.secret_mask"
                          >当前 {{ provider.secret_mask }}</em
                        >
                      </span>
                      <input
                        v-model="drafts[provider.provider]!.apiKey"
                        type="password"
                        autocomplete="new-password"
                        :placeholder="
                          provider.secret_configured
                            ? '留空保留原密钥；输入新值将覆盖'
                            : '粘贴密钥，保存后不可读取'
                        "
                      />
                    </label>
                    <label>
                      <span>每日预算</span>
                      <div class="input-affix">
                        <input
                          v-model="drafts[provider.provider]!.dailyBudgetYuan"
                          inputmode="decimal"
                        /><b>元</b>
                      </div>
                    </label>
                    <label>
                      <span>请求超时</span>
                      <div class="input-affix">
                        <input
                          v-model="drafts[provider.provider]!.timeoutSeconds"
                          inputmode="numeric"
                        /><b>秒</b>
                      </div>
                    </label>
                  </div>

                  <footer>
                    <label class="engine-switch">
                      <input
                        v-model="drafts[provider.provider]!.enabled"
                        type="checkbox"
                      />
                      <span></span>
                      启用此引擎
                    </label>
                    <div>
                      <button
                        class="button"
                        :disabled="
                          (!provider.secret_configured &&
                            !drafts[provider.provider]!.apiKey.trim()) ||
                          savingProvider === provider.provider ||
                          testingProvider === provider.provider
                        "
                        @click="runProviderTest(provider)"
                      >
                        {{
                          testingProvider === provider.provider
                            ? "正在保存并验证…"
                            : "保存并验证"
                        }}
                      </button>
                      <button
                        class="button primary"
                        :disabled="
                          savingProvider === provider.provider ||
                          testingProvider === provider.provider
                        "
                        @click="saveProvider(provider)"
                      >
                        {{
                          savingProvider === provider.provider
                            ? "保存中…"
                            : "保存配置"
                        }}
                      </button>
                    </div>
                  </footer>
                </div>
              </template>
            </article>
          </div>
        </section>

        <section class="runtime-section">
          <div class="section-title-row">
            <div>
              <span class="section-index">02</span>
              <h2>预算与安全边界</h2>
              <p>
                预算控制只约束后续调用，不会改写历史内容或已记录的模型用量。
              </p>
            </div>
          </div>
          <div class="runtime-grid">
            <article class="budget-console">
              <div>
                <span>默认单客户月度预算</span>
                <strong>¥</strong>
                <input
                  v-model="monthlyBudgetYuan"
                  aria-label="默认单客户月度预算"
                  inputmode="decimal"
                />
                <small>新客户默认值，可在后续客户设置中单独调整</small>
              </div>
              <div class="threshold-track">
                <span style="width: 80%"></span><i>80% 提醒</i><b>100% 阻止</b>
              </div>
              <button
                class="button primary"
                :disabled="savingRuntime"
                @click="saveRuntime"
              >
                {{ savingRuntime ? "保存中…" : "保存预算规则" }}
              </button>
            </article>
            <article class="guardrail-list">
              <h3>系统始终遵守</h3>
              <ul>
                <li>
                  <i>01</i
                  ><span
                    ><strong>事实优先</strong
                    >只使用已确认、允许公开的企业资料。</span
                  >
                </li>
                <li>
                  <i>02</i
                  ><span
                    ><strong>失败可见</strong
                    >Mock、超时和限流不会伪装成成功。</span
                  >
                </li>
                <li>
                  <i>03</i
                  ><span
                    ><strong>密钥隔离</strong
                    >不进入浏览器存储、日志和内容生成记录。</span
                  >
                </li>
                <li>
                  <i>04</i
                  ><span
                    ><strong>结果可追溯</strong
                    >保留模型、版本、输入输出摘要与降级原因。</span
                  >
                </li>
              </ul>
            </article>
          </div>
        </section>
        <PromptCenter />
      </template>
    </main>
  </AppShell>
</template>
