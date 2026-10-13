import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";

import RequestNotifications from "../src/components/RequestNotifications.vue";
import {
  clearRequestNotifications,
  notifyRequestError,
  notifyRequestSuccess,
  requestNotifications,
} from "../src/requestNotifications";

describe("request result notifications", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    clearRequestNotifications();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps successful and failed request results visible", () => {
    notifyRequestSuccess("GEO 诊断完成", "已更新平台评分");
    notifyRequestError("关键词生成失败", "模型返回格式异常");

    expect(requestNotifications.value).toHaveLength(2);
    expect(requestNotifications.value.map((item) => item.tone)).toEqual([
      "success",
      "error",
    ]);
  });

  it("deduplicates repeated polling errors and dismisses notifications", () => {
    notifyRequestError("数据刷新失败", "网络连接异常");
    notifyRequestError("数据刷新失败", "网络连接异常");

    expect(requestNotifications.value).toHaveLength(1);
    vi.advanceTimersByTime(8_000);
    expect(requestNotifications.value).toHaveLength(0);
  });

  it("renders a visible result card with the correct accessibility role", async () => {
    const wrapper = mount(RequestNotifications);

    notifyRequestSuccess("文章生成完成", "3 篇文章已更新");
    await nextTick();

    const card = wrapper.get('.request-notification[data-tone="success"]');
    expect(card.attributes("role")).toBe("status");
    expect(card.text()).toContain("文章生成完成");
    expect(card.text()).toContain("3 篇文章已更新");
    wrapper.unmount();
  });
});
