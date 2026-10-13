import type {
  ChannelData,
  ChannelRecommendationData,
  JobData,
  PublishingAccountData,
  PublishingChannelData,
} from "./dto";
import { apiRequest } from "./http";

export const getChannels = (): Promise<{
  items: ChannelData[];
  catalog_version: string;
}> => apiRequest("/api/v1/channels");

export const getChannelRecommendations = (
  clientId: string,
): Promise<{
  items: ChannelRecommendationData[];
  generated_at: string | null;
}> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/channel-recommendations`,
  );

export const generateChannelRecommendations = (
  clientId: string,
  idempotencyKey: string,
): Promise<{
  job_id: string;
  status: JobData["status"];
  progress: number;
}> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/channel-recommendations/generate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        brief_ids: [],
        include_ownership: [
          "operator_publishable",
          "client_required",
          "partner_cooperation",
        ],
      }),
    },
  );

export const getPublishingChannels = (): Promise<{
  items: PublishingChannelData[];
}> => apiRequest("/api/v1/publishing/channels");

export const createPublishingAccount = (
  channelId: PublishingChannelData["id"],
  displayName: string,
): Promise<PublishingAccountData> =>
  apiRequest(
    `/api/v1/publishing/channels/${encodeURIComponent(channelId)}/accounts`,
    {
      method: "POST",
      body: JSON.stringify({ display_name: displayName }),
    },
  );

export const openPublishingAccountLogin = (
  accountId: string,
): Promise<PublishingAccountData> =>
  apiRequest(
    `/api/v1/publishing/accounts/${encodeURIComponent(accountId)}/login-window`,
    {
      method: "POST",
    },
  );

export const testPublishingAccount = (
  accountId: string,
): Promise<PublishingAccountData> =>
  apiRequest(
    `/api/v1/publishing/accounts/${encodeURIComponent(accountId)}/test`,
    {
      method: "POST",
    },
  );

export const updatePublishingAccount = (
  accountId: string,
  input: { enabled?: boolean; display_name?: string; version: number },
): Promise<PublishingAccountData> =>
  apiRequest(`/api/v1/publishing/accounts/${encodeURIComponent(accountId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
