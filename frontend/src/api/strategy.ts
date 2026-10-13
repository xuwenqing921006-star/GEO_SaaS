import { apiRequest } from "./http";
import type {
  ContentFormCode,
  DiagnosticRunData,
  JobData,
  KeywordCandidateData,
  KeywordGenerationAcceptedData,
  KeywordGenerationData,
  KeywordProfileData,
  KeywordType,
  KeywordWorkspaceData,
  StrategyBundleData,
  StrategyItemData,
} from "./dto";

interface JobAccepted {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  resource_type: "diagnostic" | "strategy";
  resource_id: string | null;
}

export const createDiagnostic = (
  clientId: string,
  idempotencyKey: string,
): Promise<JobAccepted> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/diagnostics`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      scope: ["entity", "evidence", "content", "source", "visibility"],
      monitoring_window_days: 30,
    }),
  });

export const getJob = (jobId: string): Promise<JobData> =>
  apiRequest(`/api/v1/jobs/${encodeURIComponent(jobId)}`);

export const updateDiagnosticIssue = (
  issueId: string,
  input: {
    version: number;
    status: "resolved" | "ignored";
    note: string;
  },
): Promise<DiagnosticRunData["issues"][number]> =>
  apiRequest(`/api/v1/diagnostic-issues/${encodeURIComponent(issueId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });

export const getStrategy = (
  clientId: string,
): Promise<StrategyBundleData | null> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/strategy`);

export const generateStrategy = (
  clientId: string,
  diagnosticRunId: string,
  idempotencyKey: string,
  briefCount = 3,
): Promise<JobAccepted> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/strategy/generate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        diagnostic_run_id: diagnosticRunId,
        include_families: [
          "discovery",
          "recommendation",
          "scenario",
          "comparison",
          "brand_verification",
        ],
        brief_count: briefCount,
      }),
    },
  );

export const updateStrategyItem = (
  itemId: string,
  input: {
    version: number;
    text?: string;
    main_keyword?: string;
    user_intent?: string;
    keyword_type?:
      | "local_service"
      | "brand"
      | "recommendation"
      | "scenario"
      | "service_detail"
      | "comparison"
      | "transaction"
      | "trust";
    recommended_content_type?: ContentFormCode;
    priority?: 1 | 2 | 3;
    locked?: boolean;
    selected?: boolean;
    active?: boolean;
  },
): Promise<StrategyItemData> =>
  apiRequest(`/api/v1/strategy-items/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });

export const getKeywordWorkspace = (
  clientId: string,
): Promise<KeywordWorkspaceData> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/keyword-workspace`,
  );

export const saveKeywordProfile = (
  clientId: string,
  input: {
    version: number;
    primary_keyword: string;
    regions: string[];
    secondary_keywords: string[];
    keyword_types: KeywordType[];
  },
): Promise<KeywordProfileData> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/keyword-profile`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
  );

export const createKeywordGeneration = (
  clientId: string,
  input: { profile_version: number; target_count: number },
  idempotencyKey: string,
): Promise<KeywordGenerationAcceptedData> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/keyword-generations`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  );

export const getKeywordGeneration = (
  generationId: string,
): Promise<KeywordGenerationData> =>
  apiRequest(`/api/v1/keyword-generations/${encodeURIComponent(generationId)}`);

export const updateKeywordCandidate = (
  candidateId: string,
  input: { version: number; selected: boolean; active: boolean },
): Promise<KeywordCandidateData> =>
  apiRequest(`/api/v1/keyword-candidates/${encodeURIComponent(candidateId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });

export const confirmKeywordGeneration = (
  generationId: string,
  input: { version: number; candidate_ids: string[] },
): Promise<KeywordGenerationData> =>
  apiRequest(
    `/api/v1/keyword-generations/${encodeURIComponent(generationId)}/confirm`,
    { method: "POST", body: JSON.stringify(input) },
  );

export const archiveKeywordGeneration = (
  generationId: string,
  version: number,
): Promise<KeywordGenerationData> =>
  apiRequest(
    `/api/v1/keyword-generations/${encodeURIComponent(generationId)}?version=${version}`,
    { method: "DELETE" },
  );
