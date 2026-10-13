import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { render } from "@testing-library/vue";
import { mount } from "@vue/test-utils";
import { createPinia } from "pinia";

import App from "../../src/App.vue";
import { router } from "../../src/router";
import { useSessionStore } from "../../src/stores/session";
import { clearRequestNotifications } from "../../src/requestNotifications";

const prepareApplicationRuntime = async (path: string) => {
  const pinia = createPinia();
  clearRequestNotifications();
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
  useSessionStore(pinia).setSession(null);
  // The shared router may already be at /clients from the preceding test. Move
  // through the guest route so its authentication guard runs for every mount.
  await router.replace("/login");
  await router.isReady();
  await router.replace(path);
  await router.isReady();

  return { pinia, queryClient };
};

export const renderApplication = async (path = "/clients") => {
  const { pinia, queryClient } = await prepareApplicationRuntime(path);

  return {
    ...render(App, {
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }], router],
      },
    }),
    pinia,
    queryClient,
  };
};

export const mountApplication = async (path = "/clients") => {
  const { pinia, queryClient } = await prepareApplicationRuntime(path);

  return {
    wrapper: mount(App, {
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }], router],
      },
    }),
    pinia,
    queryClient,
  };
};

export const resetApplicationRuntime = async ({
  pinia,
  queryClient,
}: Awaited<ReturnType<typeof mountApplication>>): Promise<void> => {
  queryClient.clear();
  clearRequestNotifications();
  useSessionStore(pinia).setSession(null);
  await router.replace("/login");
  await router.isReady();
};
