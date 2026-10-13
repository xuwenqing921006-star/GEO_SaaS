<script setup lang="ts">
import { ConfigProvider } from "ant-design-vue";
import { onMounted, onUnmounted, ref } from "vue";
import { RouterView } from "vue-router";
import RequestNotifications from "./components/RequestNotifications.vue";

const theme = {
  token: {
    colorPrimary: "#2f6fec",
    borderRadius: 10,
    fontFamily: "Inter, PingFang SC, Microsoft YaHei, sans-serif",
  },
};
const desktopViewport = ref(
  typeof window === "undefined" || window.innerWidth >= 480,
);
const updateViewport = (): void => {
  desktopViewport.value = window.innerWidth >= 480;
};
onMounted(() => window.addEventListener("resize", updateViewport));
onUnmounted(() => window.removeEventListener("resize", updateViewport));
</script>
<template>
  <ConfigProvider :theme="theme">
    <div data-client="web">
      <span class="sr-only">GEO SaaS Web</span>
      <section v-if="!desktopViewport" class="desktop-notice">
        <section>
          <h1>桌面浏览器访问</h1>
          <p>请使用桌面浏览器访问</p>
        </section>
      </section>
      <RouterView v-else />
      <RequestNotifications />
    </div>
  </ConfigProvider>
</template>
