import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { getSession } from "../api/auth";
import { setCsrfToken } from "../api/http";
import type { SessionData } from "../api/dto";

let rememberedSession: SessionData | null = null;
let sessionInitialized = false;

export const hasSession = (): boolean => rememberedSession !== null;
export const initializeRememberedSession = async (): Promise<void> => {
  if (sessionInitialized) return;
  try {
    rememberedSession = await getSession();
    setCsrfToken(rememberedSession.csrf_token);
  } catch {
    rememberedSession = null;
  }
  sessionInitialized = true;
};

export const useSessionStore = defineStore("session", () => {
  const session = ref<SessionData | null>(rememberedSession);
  const initialized = ref(sessionInitialized);
  const isAuthenticated = computed(() => session.value !== null);

  const setSession = (next: SessionData | null): void => {
    rememberedSession = next;
    sessionInitialized = next !== null;
    session.value = next;
    initialized.value = sessionInitialized;
    setCsrfToken(next?.csrf_token ?? null);
  };
  const clearSession = (): void => {
    rememberedSession = null;
    sessionInitialized = true;
    session.value = null;
    initialized.value = true;
    setCsrfToken(null);
  };
  const initialize = async (): Promise<void> => {
    if (initialized.value) return;
    await initializeRememberedSession();
    session.value = rememberedSession;
    initialized.value = true;
  };
  return {
    session,
    initialized,
    isAuthenticated,
    setSession,
    clearSession,
    initialize,
  };
});
