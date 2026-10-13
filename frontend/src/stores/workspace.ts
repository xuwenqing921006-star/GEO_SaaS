import { defineStore } from "pinia";
import { ref } from "vue";
import type { ClientSummary } from "../api/dto";

export type PendingNavigation =
  | { type: "client"; clientId: string }
  | { type: "route"; fullPath: string }
  | { type: "logout" }
  | null;

export const useWorkspaceStore = defineStore("workspace", () => {
  const currentClientId = ref("");
  const currentClient = ref<ClientSummary | null>(null);
  const isDirty = ref(false);
  const pendingClientId = ref("");
  const pendingNavigation = ref<PendingNavigation>(null);
  const setCurrentClient = (client: ClientSummary | null): void => {
    currentClient.value = client;
    currentClientId.value = client?.id ?? "";
  };
  const clear = (): void => {
    currentClientId.value = "";
    currentClient.value = null;
    isDirty.value = false;
    pendingClientId.value = "";
    pendingNavigation.value = null;
  };
  return {
    currentClientId,
    currentClient,
    isDirty,
    pendingClientId,
    pendingNavigation,
    setCurrentClient,
    clear,
  };
});
