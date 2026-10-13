import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ProviderName,
  ProviderSettingData,
  SettingsData,
} from "../src/api/dto";
import { ApiError } from "../src/api/http";
import SettingsView from "../src/views/SettingsView.vue";

const settingsApi = vi.hoisted(() => ({
  getSettings: vi.fn(),
  testProvider: vi.fn(),
  updateProvider: vi.fn(),
  updateRuntime: vi.fn(),
}));

vi.mock("../src/api/settings", () => settingsApi);

const provider = (
  providerName: ProviderName,
  version: number,
): ProviderSettingData => ({
  provider: providerName,
  enabled: true,
  base_url:
    providerName === "qwen"
      ? "https://dashscope.aliyuncs.com/compatible-mode/v1"
      : providerName === "doubao"
        ? "https://ark.cn-beijing.volces.com/api/v3"
        : "https://api.deepseek.com/v1",
  workspace_id: null,
  writer_model:
    providerName === "deepseek"
      ? null
      : providerName === "doubao"
        ? "doubao-seed-2-0-lite-260215"
        : "qwen3.7-plus",
  reviewer_model: providerName === "deepseek" ? "deepseek-v4-pro" : null,
  fallback_model: providerName === "deepseek" ? "deepseek-v4-flash" : null,
  daily_budget_cny_fen: 3000,
  timeout_seconds: 45,
  secret_configured: true,
  secret_mask: "••••test",
  last_tested_at: null,
  last_test_status: "not_tested",
  version,
});

const settings = (deepseekVersion: number): SettingsData => ({
  providers: [
    provider("deepseek", deepseekVersion),
    provider("doubao", 1),
    provider("qwen", 1),
  ],
  runtime: {
    timezone: "Asia/Shanghai",
    max_upload_mb: 30,
    max_upload_files: 20,
    job_retry_limit: 3,
    job_poll_seconds: 2,
    default_client_monthly_budget_cny_fen: 30000,
    version: 1,
  },
  catalogs: {
    provider_catalog_version: "test",
    model_policy_version: "test",
  },
});

const mountSettings = () =>
  mount(SettingsView, {
    global: {
      stubs: {
        AppShell: { template: "<div><slot /></div>" },
        PromptCenter: true,
      },
    },
  });

const buttonByText = (
  wrapper: ReturnType<typeof mountSettings>,
  text: string,
) => wrapper.findAll("button").find((button) => button.text().trim() === text)!;

describe("settings provider version recovery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reloads the current version after a 409 save conflict", async () => {
    settingsApi.getSettings
      .mockResolvedValueOnce(settings(1))
      .mockResolvedValueOnce(settings(2));
    settingsApi.updateProvider
      .mockRejectedValueOnce(
        new ApiError(409, {
          code: 40901,
          message: "模型配置已被更新，请刷新后重试",
          data: {
            field_errors: [],
            retryable: false,
            provider: null,
            job_id: null,
          },
          request_id: "request-1",
        }),
      )
      .mockResolvedValueOnce(provider("deepseek", 3));

    const wrapper = mountSettings();
    await flushPromises();

    await buttonByText(wrapper, "保存配置").trigger("click");
    await flushPromises();

    expect(settingsApi.getSettings).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("模型配置已被更新，请刷新后重试");

    await buttonByText(wrapper, "保存配置").trigger("click");
    await flushPromises();

    expect(settingsApi.updateProvider.mock.calls[1]?.[1].version).toBe(2);
  });

  it("reloads the version after a failed probe and blocks concurrent save", async () => {
    settingsApi.getSettings
      .mockResolvedValueOnce(settings(1))
      .mockResolvedValueOnce(settings(3));
    settingsApi.updateProvider
      .mockResolvedValueOnce(provider("deepseek", 2))
      .mockResolvedValueOnce(provider("deepseek", 4));

    let rejectProbe: ((reason: unknown) => void) | undefined;
    settingsApi.testProvider.mockReturnValueOnce(
      new Promise((_, reject) => {
        rejectProbe = reject;
      }),
    );

    const wrapper = mountSettings();
    await flushPromises();

    await buttonByText(wrapper, "保存并验证").trigger("click");
    await flushPromises();

    expect(
      buttonByText(wrapper, "保存配置").attributes("disabled"),
    ).toBeDefined();

    rejectProbe?.(new Error("模型连接测试失败"));
    await flushPromises();

    expect(settingsApi.getSettings).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("模型连接测试失败");

    await buttonByText(wrapper, "保存配置").trigger("click");
    await flushPromises();

    expect(settingsApi.updateProvider.mock.calls[1]?.[1].version).toBe(3);
  });
});
