<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, useId } from "vue";

import { isTopModal, registerModal, unregisterModal } from "./modalCoordinator";

const props = withDefaults(
  defineProps<{
    title: string;
    size?: "small" | "medium" | "large";
    closeDisabled?: boolean;
  }>(),
  { size: "medium", closeDisabled: false },
);
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLElement | null>(null);
const titleId = useId();
const modalInstanceId = Symbol("modal");
let previousFocus: HTMLElement | null = null;

onMounted(async () => {
  previousFocus = document.activeElement as HTMLElement | null;
  registerModal(modalInstanceId);
  window.addEventListener("keydown", handleGlobalKeydown);
  await nextTick();
  dialog.value
    ?.querySelector<HTMLElement>("input, button, select, textarea")
    ?.focus();
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  unregisterModal(modalInstanceId);
  previousFocus?.focus();
});
const close = (): void => {
  if (!props.closeDisabled) emit("close");
};
const handleGlobalKeydown = (event: KeyboardEvent): void => {
  if (event.key === "Escape" && isTopModal(modalInstanceId)) close();
};
const trapFocus = (event: KeyboardEvent): void => {
  if (event.key !== "Tab" || !dialog.value) return;
  const controls = [
    ...dialog.value.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex='-1'])",
    ),
  ];
  const first = controls[0];
  const last = controls.at(-1);
  if (!first || !last) return;
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
};
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade" appear>
      <div class="modal-backdrop" @mousedown.self="close">
        <section
          ref="dialog"
          class="modal"
          :class="`modal--${props.size}`"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          @keydown="trapFocus"
        >
          <header class="modal-header">
            <div>
              <span class="modal-kicker">GEO 工作台</span>
              <h2 :id="titleId">{{ props.title }}</h2>
            </div>
            <button
              class="icon-button"
              type="button"
              aria-label="关闭"
              title="关闭（Esc）"
              :disabled="props.closeDisabled"
              @click="close"
            >
              <span aria-hidden="true">×</span>
            </button>
          </header>
          <div class="modal-body">
            <slot />
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
