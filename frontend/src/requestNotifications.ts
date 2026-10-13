import { readonly, ref } from "vue";

export type RequestNotificationTone = "success" | "error" | "info" | "warning";

export interface RequestNotification {
  id: number;
  tone: RequestNotificationTone;
  title: string;
  detail: string;
}

const notificationItems = ref<RequestNotification[]>([]);
const timers = new Map<number, number>();
let nextNotificationId = 1;

export const requestNotifications = readonly(notificationItems);

export const dismissRequestNotification = (id: number): void => {
  const timer = timers.get(id);
  if (timer !== undefined) window.clearTimeout(timer);
  timers.delete(id);
  notificationItems.value = notificationItems.value.filter(
    (notification) => notification.id !== id,
  );
};

export const clearRequestNotifications = (): void => {
  for (const timer of timers.values()) window.clearTimeout(timer);
  timers.clear();
  notificationItems.value = [];
};

export const notifyRequestResult = (
  tone: RequestNotificationTone,
  title: string,
  detail = "",
  durationMs = tone === "error" ? 8_000 : 6_000,
): void => {
  const normalizedTitle = title.trim();
  const normalizedDetail = detail.trim();
  if (!normalizedTitle) return;
  const duplicate = notificationItems.value.find(
    (notification) =>
      notification.tone === tone &&
      notification.title === normalizedTitle &&
      notification.detail === normalizedDetail,
  );
  if (duplicate) return;

  const id = nextNotificationId;
  nextNotificationId += 1;
  notificationItems.value = [
    ...notificationItems.value.slice(-3),
    { id, tone, title: normalizedTitle, detail: normalizedDetail },
  ];
  timers.set(
    id,
    window.setTimeout(() => dismissRequestNotification(id), durationMs),
  );
};

export const notifyRequestSuccess = (title: string, detail = ""): void =>
  notifyRequestResult("success", title, detail);

export const notifyRequestError = (title: string, detail = ""): void =>
  notifyRequestResult("error", title, detail);

export const notifyRequestInfo = (title: string, detail = ""): void =>
  notifyRequestResult("info", title, detail);

export const notifyRequestWarning = (title: string, detail = ""): void =>
  notifyRequestResult("warning", title, detail);
