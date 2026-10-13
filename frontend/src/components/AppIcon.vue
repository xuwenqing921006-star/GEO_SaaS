<script setup lang="ts">
defineProps<{
  name:
    | "brand"
    | "clients"
    | "knowledge"
    | "diagnostics"
    | "strategy"
    | "content"
    | "publishing"
    | "channels"
    | "monitoring"
    | "settings";
}>();
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'brand'">
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </template>
    <template v-else-if="name === 'clients'">
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </template>
    <template v-else-if="name === 'knowledge'">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22Z" />
      <path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5A2.5 2.5 0 0 1 20 22Z" />
    </template>
    <template v-else-if="name === 'diagnostics'">
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3.5V6M20.5 12H18M12 20.5V18M3.5 12H6" />
    </template>
    <template v-else-if="name === 'strategy'">
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'content'">
      <path d="M6 3h8l4 4v14H6Z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </template>
    <template v-else-if="name === 'publishing'">
      <path d="M5 4h10l4 4v12H5Z" />
      <path d="M15 4v5h5M9 15h6M12 18v-6m0 0-2.5 2.5M12 12l2.5 2.5" />
    </template>
    <template v-else-if="name === 'channels'">
      <path d="m21 3-8.2 18-2.2-7.6L3 11.2Z" />
      <path d="m10.6 13.4 4-4" />
    </template>
    <template v-else-if="name === 'monitoring'">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20V7" />
      <path d="M2 20h22" />
    </template>
    <template v-else>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="8" cy="17" r="2" />
    </template>
  </svg>
</template>
