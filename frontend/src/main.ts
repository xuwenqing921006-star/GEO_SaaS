import { createApp } from "vue";
import { createPinia } from "pinia";
import { QueryCache, QueryClient, VueQueryPlugin } from "@tanstack/vue-query";

import App from "./App.vue";
import { router } from "./router";
import "./styles.css";
import "./responsive.css";
import "./t003.css";
import "./bright-theme.css";
import "./request-notifications.css";
import { ApiError } from "./api/http";
import { notifyRequestError } from "./requestNotifications";

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) return;
      notifyRequestError(
        "数据刷新失败",
        error instanceof Error ? error.message : "网络连接异常，请稍后重试",
      );
    },
  }),
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: { retry: false },
  },
});
createApp(App)
  .use(createPinia())
  .use(VueQueryPlugin, { queryClient })
  .use(router)
  .mount("#app");
