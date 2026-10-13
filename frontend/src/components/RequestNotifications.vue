<script setup lang="ts">
import {
  dismissRequestNotification,
  requestNotifications,
} from "../requestNotifications";

const toneIcon = {
  success: "✓",
  error: "!",
  info: "i",
  warning: "!",
} as const;
</script>

<template>
  <aside class="request-notification-region" aria-live="polite">
    <TransitionGroup name="request-notification">
      <article
        v-for="notification in requestNotifications"
        :key="notification.id"
        class="request-notification"
        :data-tone="notification.tone"
        :role="notification.tone === 'error' ? 'alert' : 'status'"
      >
        <span class="request-notification-icon" aria-hidden="true">
          {{ toneIcon[notification.tone] }}
        </span>
        <div>
          <strong>{{ notification.title }}</strong>
          <p v-if="notification.detail">{{ notification.detail }}</p>
        </div>
        <button
          type="button"
          aria-label="关闭通知"
          @click="dismissRequestNotification(notification.id)"
        >
          ×
        </button>
      </article>
    </TransitionGroup>
  </aside>
</template>
