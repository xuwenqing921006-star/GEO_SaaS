import type {
  ProviderName,
  ProviderSettingData,
  ProviderTestData,
  RuntimeSettingData,
  SettingsData,
} from "./dto";
import { apiRequest } from "./http";

export interface ProviderSettingInput {
  version: number;
  enabled: boolean;
  base_url: string;
  workspace_id: string | null;
  writer_model: string | null;
  reviewer_model: string | null;
  fallback_model: string | null;
  daily_budget_cny_fen: number;
  timeout_seconds: number;
  api_key: string | null;
}

export const getSettings = (): Promise<SettingsData> =>
  apiRequest("/api/v1/settings");

export const updateProvider = (
  provider: ProviderName,
  input: ProviderSettingInput,
): Promise<ProviderSettingData> =>
  apiRequest(`/api/v1/settings/providers/${provider}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });

export const testProvider = (
  provider: ProviderName,
): Promise<ProviderTestData> =>
  apiRequest(`/api/v1/settings/providers/${provider}/test`, {
    method: "POST",
    body: JSON.stringify({
      test_type: "structured_output",
      use_saved_secret: true,
      api_key: null,
    }),
  });

export const updateRuntime = (
  version: number,
  defaultClientMonthlyBudgetCnyFen: number,
): Promise<RuntimeSettingData> =>
  apiRequest("/api/v1/settings/runtime", {
    method: "PATCH",
    body: JSON.stringify({
      version,
      default_client_monthly_budget_cny_fen: defaultClientMonthlyBudgetCnyFen,
    }),
  });
