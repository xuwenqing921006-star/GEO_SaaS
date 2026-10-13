<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed, reactive, ref, watch } from "vue";
import {
  createPublishingAccount,
  getPublishingChannels,
  openPublishingAccountLogin,
  testPublishingAccount,
  updatePublishingAccount,
} from "../api/channels";
import type { PublishingAccountData, PublishingChannelData } from "../api/dto";
import AppShell from "../components/AppShell.vue";
import {
  notifyRequestError,
  notifyRequestSuccess,
  notifyRequestWarning,
} from "../requestNotifications";

const channelsQuery = useQuery({
  queryKey: ["publishing-channels"],
  queryFn: getPublishingChannels,
  refetchInterval: 5 * 60_000,
});
const actionMessage = ref("");
const actionError = ref("");
const busyAccountId = ref("");
const addingChannelId = ref("");
const accountDrafts = reactive<Record<string, string>>({});

watch(actionMessage, (message) => {
  if (message && !message.startsWith("正在"))
    notifyRequestSuccess("渠道操作完成", message);
});
watch(actionError, (message) => {
  if (message) notifyRequestError("渠道操作未完成", message);
});

const sessionAlertAccounts = computed(() =>
  (channelsQuery.data.value?.items ?? []).flatMap((channel) =>
    channel.accounts
      .filter((account) =>
        [
          "check_due_soon",
          "check_due",
          "expired",
          "verification_required",
          "error",
        ].includes(account.session_health),
      )
      .map((account) => ({ channel, account })),
  ),
);
const criticalSessionCount = computed(
  () =>
    sessionAlertAccounts.value.filter(({ account }) =>
      ["expired", "verification_required", "error"].includes(
        account.session_health,
      ),
    ).length,
);
watch(
  criticalSessionCount,
  (count, previous = 0) => {
    if (count > previous)
      notifyRequestWarning(
        "发布账号需要处理",
        `${count} 个账号登录状态异常，请在发布前重新登录或检测连接`,
      );
  },
  { immediate: true },
);
const platformMark: Record<PublishingChannelData["id"], string> = {
  toutiao: "头",
  baijia: "百",
  netease: "网",
  sohu: "搜",
  penguin: "企",
  yidian: "一",
};
const formatDateTime = (value: string | null): string => {
  if (!value) return "尚未检测";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
};
const resetFeedback = (): void => {
  actionMessage.value = "";
  actionError.value = "";
};
const refresh = async (): Promise<void> => {
  await channelsQuery.refetch();
};
const addAccount = async (channel: PublishingChannelData): Promise<void> => {
  const displayName = (accountDrafts[channel.id] ?? "").trim();
  if (!displayName) {
    actionError.value = "请先填写账号备注，例如“企业主账号”";
    return;
  }
  resetFeedback();
  addingChannelId.value = channel.id;
  try {
    await createPublishingAccount(channel.id, displayName);
    accountDrafts[channel.id] = "";
    actionMessage.value = `${channel.name}账号已创建，请打开登录窗口完成登录`;
    await refresh();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : "账号创建失败";
  } finally {
    addingChannelId.value = "";
  }
};
const openLogin = async (
  channel: PublishingChannelData,
  account: PublishingAccountData,
): Promise<void> => {
  resetFeedback();
  busyAccountId.value = account.id;
  try {
    await openPublishingAccountLogin(account.id);
    actionMessage.value = `已使用${channel.name}“${account.display_name}”原来的独立登录环境打开窗口。扫码或验证后关闭窗口，再点击检测连接即可续期。`;
    await refresh();
  } catch (error) {
    actionError.value =
      error instanceof Error ? error.message : "登录窗口打开失败";
  } finally {
    busyAccountId.value = "";
  }
};
const testConnection = async (
  channel: PublishingChannelData,
  account: PublishingAccountData,
): Promise<void> => {
  resetFeedback();
  busyAccountId.value = account.id;
  actionMessage.value = `正在检测${channel.name}“${account.display_name}”…`;
  try {
    const result = await testPublishingAccount(account.id);
    if (result.connection_status !== "connected") {
      actionMessage.value = "";
      actionError.value = result.last_error ?? "尚未检测到有效登录状态";
    } else {
      actionMessage.value = `${channel.name}连接成功，可以启用自动发布`;
    }
    await refresh();
  } catch (error) {
    actionMessage.value = "";
    actionError.value = error instanceof Error ? error.message : "连接检测失败";
  } finally {
    busyAccountId.value = "";
  }
};
const toggleAccount = async (
  channel: PublishingChannelData,
  account: PublishingAccountData,
): Promise<void> => {
  resetFeedback();
  busyAccountId.value = account.id;
  try {
    const result = await updatePublishingAccount(account.id, {
      enabled: !account.enabled,
      version: account.version,
    });
    actionMessage.value = `${channel.name}“${account.display_name}”自动发布已${result.enabled ? "启用" : "暂停"}`;
    await refresh();
  } catch (error) {
    actionError.value =
      error instanceof Error ? error.message : "账号配置更新失败";
  } finally {
    busyAccountId.value = "";
  }
};
</script>

<template>
  <AppShell>
    <main class="workspace publishing-page">
      <header class="page-head publishing-head">
        <div>
          <p class="eyebrow">P06 · 自动发布</p>
          <h1>发布账号</h1>
          <p>
            每个平台最多连接 5
            个账号。系统每天自动检测一次，并在每次发布前再次核验；异常只会暂停对应账号。
          </p>
        </div>
        <div class="safety-card">
          <span aria-hidden="true">✓</span>
          <div>
            <strong>不保存账号密码</strong
            ><small>每个账号保留独立的本机浏览器会话</small>
          </div>
        </div>
      </header>

      <section class="flow-strip" aria-label="使用步骤">
        <div>
          <b>1</b
          ><span
            ><strong>添加账号</strong><small>填写便于识别的备注</small></span
          >
        </div>
        <div>
          <b>2</b
          ><span
            ><strong>登录并检测</strong><small>每个账号独立完成</small></span
          >
        </div>
        <div>
          <b>3</b
          ><span
            ><strong>多选发布</strong><small>在内容工作台选择目标</small></span
          >
        </div>
      </section>

      <section
        v-if="sessionAlertAccounts.length"
        class="session-alert"
        :data-tone="criticalSessionCount ? 'critical' : 'warning'"
        role="alert"
      >
        <span class="session-alert__icon" aria-hidden="true">!</span>
        <div>
          <strong>
            {{
              criticalSessionCount
                ? `${criticalSessionCount} 个发布账号需要重新登录或验证`
                : `${sessionAlertAccounts.length} 个账号即将或已经到自动复检时间`
            }}
          </strong>
          <p>
            已失效账号不会继续发布。点击对应账号的“重新登录”，系统会打开原来的浏览器登录环境。
          </p>
        </div>
      </section>

      <p v-if="actionMessage" class="inline-success" role="status">
        {{ actionMessage }}
      </p>
      <p v-if="actionError" class="inline-error" role="alert">
        {{ actionError }}
      </p>

      <section
        v-if="channelsQuery.isPending.value"
        class="panel loading-panel"
        aria-busy="true"
      >
        <span class="loading-orbit" />
        <p>正在载入发布账号…</p>
      </section>
      <section
        v-else-if="channelsQuery.isError.value"
        class="panel error-panel"
      >
        <h2>发布账号暂时无法载入</h2>
        <button class="button primary" @click="channelsQuery.refetch()">
          重新载入
        </button>
      </section>

      <section v-else class="platform-list">
        <article
          v-for="channel in channelsQuery.data.value?.items ?? []"
          :key="channel.id"
          class="platform-card"
        >
          <header class="platform-card__head">
            <div class="platform-identity">
              <span class="platform-mark" :data-platform="channel.id">{{
                platformMark[channel.id]
              }}</span>
              <div>
                <h2>{{ channel.name }}</h2>
                <p>{{ channel.description }}</p>
                <small
                  v-if="channel.id === 'yidian'"
                  class="platform-subject-note"
                >
                  系统可连接最多 5
                  个独立会话；一点号同一企业主体按平台规则最多认证 2 个账号。
                </small>
              </div>
            </div>
            <div class="platform-summary">
              <span
                ><strong>{{ channel.account_count }}</strong
                >/{{ channel.max_accounts }} 个账号</span
              >
              <span
                ><strong>{{ channel.enabled_count }}</strong> 个已启用</span
              >
              <a
                :href="channel.official_url"
                target="_blank"
                rel="noopener noreferrer"
                >打开后台 ↗</a
              >
            </div>
          </header>

          <details
            v-if="channel.generation_spec"
            class="platform-rules"
            :open="channel.id === 'netease' || channel.id === 'yidian'"
          >
            <summary>
              <span>发文规范</span>
              <small>生成前约束内容，发布时再次校验</small>
            </summary>
            <div class="platform-rules__body">
              <div class="platform-rules__metrics">
                <span>
                  标题 {{ channel.generation_spec.title_min_characters }}–{{
                    channel.generation_spec.title_max_characters
                  }}
                  字
                </span>
                <span>
                  正文至少
                  {{ channel.generation_spec.minimum_body_characters }} 字
                </span>
                <span>
                  正文图片
                  {{
                    channel.generation_spec.image_requirements
                      .minimum_body_images
                  }}–{{
                    channel.generation_spec.image_requirements
                      .maximum_body_images
                  }}
                  张
                </span>
                <span>
                  封面
                  {{
                    channel.generation_spec.image_requirements.cover_width
                  }}×{{
                    channel.generation_spec.image_requirements.cover_height
                  }}
                </span>
                <span v-if="channel.generation_spec.daily_publication_limit">
                  每日最多
                  {{ channel.generation_spec.daily_publication_limit }} 篇
                </span>
                <span
                  v-if="
                    channel.generation_spec.image_requirements.cover_source ===
                    'body'
                  "
                >
                  封面从正文图片选择
                </span>
              </div>
              <ul>
                <li
                  v-for="rule in channel.generation_spec.content_requirements"
                  :key="rule"
                >
                  {{ rule }}
                </li>
                <li>
                  {{ channel.generation_spec.image_requirements.requirement }}
                </li>
              </ul>
            </div>
          </details>

          <div v-if="channel.accounts.length" class="account-list">
            <article
              v-for="account in channel.accounts"
              :key="account.id"
              class="account-row"
              :data-health="account.session_health"
            >
              <div class="account-main">
                <span
                  class="status-dot"
                  :data-status="account.connection_status"
                  aria-hidden="true"
                />
                <div>
                  <strong>{{ account.display_name }}</strong>
                  <small>{{
                    account.account_name ?? "尚未识别平台昵称"
                  }}</small>
                </div>
              </div>
              <div class="account-status">
                <span :data-health="account.session_health">{{
                  account.session_health_label
                }}</span>
                <small
                  >最近检测：{{
                    formatDateTime(account.last_checked_at)
                  }}</small
                >
              </div>
              <p
                class="session-health-note"
                :data-health="account.session_health"
              >
                {{ account.session_health_message }}
                <small v-if="account.next_automatic_check_at">
                  下次检测：{{
                    formatDateTime(account.next_automatic_check_at)
                  }}
                </small>
              </p>
              <div class="account-actions">
                <button
                  class="button secondary"
                  :disabled="busyAccountId === account.id"
                  @click="openLogin(channel, account)"
                >
                  {{
                    account.connection_status === "disconnected"
                      ? "打开登录"
                      : account.connection_status === "awaiting_login"
                        ? "继续登录"
                        : "重新登录"
                  }}
                </button>
                <button
                  class="button secondary"
                  :disabled="busyAccountId === account.id"
                  @click="testConnection(channel, account)"
                >
                  检测连接
                </button>
                <button
                  class="button"
                  :class="account.enabled ? 'secondary' : 'primary'"
                  :disabled="
                    busyAccountId === account.id ||
                    account.connection_status !== 'connected'
                  "
                  @click="toggleAccount(channel, account)"
                >
                  {{ account.enabled ? "暂停" : "启用" }}
                </button>
              </div>
            </article>
          </div>
          <div v-else class="account-empty">
            尚未添加账号。添加后，每个账号会创建独立的登录环境。
          </div>

          <footer class="add-account-row">
            <label :for="`account-${channel.id}`">账号备注</label>
            <input
              :id="`account-${channel.id}`"
              v-model="accountDrafts[channel.id]"
              :disabled="channel.account_count >= channel.max_accounts"
              :placeholder="
                channel.account_count >= channel.max_accounts
                  ? '已达到 5 个账号上限'
                  : `例如：${channel.name}主账号`
              "
              maxlength="100"
              @keyup.enter="addAccount(channel)"
            />
            <button
              class="button primary"
              :disabled="
                addingChannelId === channel.id ||
                channel.account_count >= channel.max_accounts
              "
              @click="addAccount(channel)"
            >
              {{ addingChannelId === channel.id ? "添加中…" : "添加账号" }}
            </button>
          </footer>
        </article>
      </section>

      <p class="publishing-note">
        平台出现验证码、身份验证或内容违规提示时，系统不会绕过验证，也不会把任务误标为发布成功。
      </p>
    </main>
  </AppShell>
</template>

<style scoped>
.publishing-page {
  display: grid;
  gap: 18px;
}
.publishing-head {
  align-items: flex-start;
}
.safety-card {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px 18px;
  border: 1px solid #cfe0ff;
  border-radius: 16px;
  background: #f5f9ff;
  color: #174b9b;
}
.safety-card > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: #e1ecff;
  color: #2563eb;
  font-weight: 800;
}
.safety-card div {
  display: grid;
  gap: 2px;
}
.safety-card small {
  color: #6680a6;
}
.flow-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  overflow: hidden;
  border: 1px solid #dce6f4;
  border-radius: 16px;
  background: #dce6f4;
}
.flow-strip > div {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 20px;
  background: #fff;
}
.flow-strip b {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  background: #eaf2ff;
  color: #2563eb;
}
.flow-strip span {
  display: grid;
}
.flow-strip small {
  margin-top: 2px;
  color: #75849a;
}
.session-alert {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 16px 18px;
  border: 1px solid #f2cf87;
  border-radius: 16px;
  background: linear-gradient(120deg, #fffaf0, #fff6dc);
  color: #7b5410;
  box-shadow: 0 10px 28px rgba(164, 111, 18, 0.08);
}
.session-alert[data-tone="critical"] {
  border-color: #f0b8b3;
  background: linear-gradient(120deg, #fff8f7, #ffefed);
  color: #9f3028;
}
.session-alert__icon {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: #f5b942;
  color: #fff;
  font-weight: 900;
}
.session-alert[data-tone="critical"] .session-alert__icon {
  background: #e45f55;
}
.session-alert div {
  display: grid;
  gap: 4px;
}
.session-alert p {
  margin: 0;
  color: inherit;
  opacity: 0.82;
}
.platform-list {
  display: grid;
  gap: 16px;
}
.platform-card {
  overflow: hidden;
  border: 1px solid #dbe5f2;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 12px 32px rgba(39, 76, 119, 0.07);
}
.platform-card__head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px;
  border-bottom: 1px solid #e8eef6;
  background: linear-gradient(120deg, #fff 55%, #f4f8ff);
}
.platform-identity {
  display: flex;
  gap: 14px;
  align-items: center;
}
.platform-identity h2 {
  margin: 0 0 4px;
  color: #12345b;
}
.platform-identity p {
  margin: 0;
  color: #6d7f95;
}
.platform-mark {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: #3478f6;
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  box-shadow: 0 8px 20px rgba(52, 120, 246, 0.24);
}
.platform-mark[data-platform="sohu"] {
  background: #1685e5;
}
.platform-mark[data-platform="baijia"] {
  background: #3867f0;
}
.platform-mark[data-platform="netease"] {
  background: #e65353;
}
.platform-mark[data-platform="penguin"] {
  background: #13a8a8;
}
.platform-mark[data-platform="yidian"] {
  background: #f59e0b;
}
.platform-subject-note {
  display: block;
  margin-top: 4px;
  color: #9a5b00;
  font-size: 12px;
  line-height: 1.5;
}
.platform-summary {
  display: flex;
  gap: 18px;
  align-items: center;
  color: #6b7d91;
}
.platform-summary strong {
  color: #184a91;
}
.platform-summary a {
  color: #2563eb;
  text-decoration: none;
}
.platform-rules {
  border-bottom: 1px solid #e8eef6;
  background: #fbfdff;
}
.platform-rules summary {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 12px 22px;
  color: #214f88;
  cursor: pointer;
  list-style: none;
}
.platform-rules summary::-webkit-details-marker {
  display: none;
}
.platform-rules summary::before {
  content: "+";
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 7px;
  background: #eaf2ff;
  color: #2563eb;
  font-weight: 800;
}
.platform-rules[open] summary::before {
  content: "−";
}
.platform-rules summary small {
  color: #7b8ba1;
}
.platform-rules__body {
  display: grid;
  gap: 12px;
  padding: 0 22px 16px 52px;
}
.platform-rules__metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.platform-rules__metrics span {
  padding: 5px 10px;
  border: 1px solid #d8e5f8;
  border-radius: 999px;
  background: #f3f7ff;
  color: #315b92;
  font-size: 13px;
}
.platform-rules ul {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
  color: #5c6f86;
  font-size: 13px;
}
.account-list {
  display: grid;
}
.account-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 190px minmax(160px, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 16px 22px;
  border-bottom: 1px solid #edf1f7;
}
.account-row[data-health="check_due_soon"],
.account-row[data-health="check_due"] {
  background: #fffdf7;
}
.account-row[data-health="expired"],
.account-row[data-health="verification_required"],
.account-row[data-health="error"] {
  background: #fff9f8;
}
.account-main {
  display: flex;
  gap: 10px;
  align-items: center;
}
.account-main > div,
.account-status {
  display: grid;
  gap: 3px;
}
.account-main small,
.account-status small {
  color: #7b899b;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #a8b2c0;
  box-shadow: 0 0 0 5px #f0f3f7;
}
.status-dot[data-status="connected"] {
  background: #22a879;
  box-shadow: 0 0 0 5px #e5f7f0;
}
.status-dot[data-status="needs_verification"],
.status-dot[data-status="needs_login"] {
  background: #e59b2b;
  box-shadow: 0 0 0 5px #fff4df;
}
.status-dot[data-status="error"] {
  background: #df5e55;
  box-shadow: 0 0 0 5px #ffecea;
}
.account-status > span {
  width: max-content;
  padding: 3px 9px;
  border-radius: 999px;
  background: #eef3f9;
  color: #597087;
  font-size: 13px;
}
.account-status > span[data-health="healthy"] {
  background: #e7f7f1;
  color: #087c5d;
}
.account-status > span[data-health="check_due_soon"],
.account-status > span[data-health="check_due"],
.account-status > span[data-health="awaiting_login"] {
  background: #fff0cf;
  color: #9a5c00;
}
.account-status > span[data-health="expired"],
.account-status > span[data-health="verification_required"],
.account-status > span[data-health="error"] {
  background: #ffe8e5;
  color: #b63d34;
}
.session-health-note {
  display: grid;
  gap: 3px;
  margin: 0;
  color: #607286;
  font-size: 13px;
}
.session-health-note small {
  color: #8795a6;
}
.session-health-note[data-health="expired"],
.session-health-note[data-health="verification_required"],
.session-health-note[data-health="error"] {
  color: #b24a42;
  font-weight: 650;
}
.account-actions {
  display: flex;
  gap: 8px;
}
.account-empty {
  padding: 28px 22px;
  color: #7a899c;
  text-align: center;
}
.add-account-row {
  display: grid;
  grid-template-columns: auto minmax(220px, 420px) auto 1fr;
  gap: 10px;
  align-items: center;
  padding: 15px 22px;
  background: #f8faff;
}
.add-account-row label {
  color: #516579;
  font-weight: 700;
}
.add-account-row input {
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid #cfdbea;
  border-radius: 10px;
  background: #fff;
}
.publishing-note {
  margin: 0;
  padding: 14px 18px;
  border-radius: 12px;
  background: #f4f7fb;
  color: #687b91;
}
@media (max-width: 1000px) {
  .platform-card__head {
    display: grid;
  }
  .platform-summary {
    flex-wrap: wrap;
  }
  .account-row {
    grid-template-columns: 1fr 1fr;
  }
  .account-actions {
    grid-column: 1/-1;
  }
  .flow-strip {
    grid-template-columns: 1fr;
  }
  .add-account-row {
    grid-template-columns: 1fr;
  }
  .add-account-row label {
    display: none;
  }
}
</style>
