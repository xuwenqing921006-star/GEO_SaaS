import type {
  MonitoringBatchData,
  MonitoringEvaluationData,
  MonitoringMetricsData,
  OptimizationActionData,
  MonitoringQuestionData,
  MonitoringQuestionSetData,
  MonitoringSampleData,
  PlatformData,
} from "./dto";
import { ApiError, apiRequest } from "./http";

export const getPlatforms = (): Promise<{
  items: PlatformData[];
  catalog_version: string;
}> => apiRequest("/api/v1/monitoring/platforms");

export const getQuestionSets = (
  clientId: string,
): Promise<{ items: MonitoringQuestionSetData[] }> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/question-sets`);

export const createQuestionSet = (
  clientId: string,
  input: {
    name: string;
    frozen: boolean;
    questions: MonitoringQuestionData[];
  },
): Promise<MonitoringQuestionSetData> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/question-sets`, {
    method: "POST",
    body: JSON.stringify(input),
  });

export const createMonitoringBatch = (
  clientId: string,
  input: {
    question_set_id: string;
    platform_ids: string[];
    api_sample_count: number;
    manual_placeholders: boolean;
  },
  idempotencyKey: string,
): Promise<{
  batch: MonitoringBatchData;
  job: { id: string; job_type: "monitoring_batch"; status: string };
}> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/monitoring-batches`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  );

export const getLatestMonitoringBatch = async (
  clientId: string,
): Promise<MonitoringBatchData | null> => {
  try {
    return await apiRequest(
      `/api/v1/clients/${encodeURIComponent(clientId)}/monitoring-batches/latest`,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
};

export const saveManualSamples = (
  batchId: string,
  items: {
    sample_id: string;
    status: "succeeded" | "failed";
    raw_answer?: string;
    failure_reason?: string;
    asked_at: string;
  }[],
): Promise<{ items: MonitoringSampleData[] }> =>
  apiRequest(
    `/api/v1/monitoring-batches/${encodeURIComponent(batchId)}/manual-samples`,
    { method: "POST", body: JSON.stringify({ items }) },
  );

export const updateMonitoringEvaluation = (
  sampleId: string,
  input: {
    version: number | null;
    brand_found: boolean;
    correctly_associated: boolean;
    recommended: boolean;
    recommendation_supported: boolean | null;
    facts_accurate: boolean | null;
    source_visible: boolean;
    mentioned_name: string | null;
    reasons: string[];
    incorrect_facts: Record<string, unknown>[];
    visible_sources: Record<string, unknown>[];
    note: string | null;
  },
): Promise<MonitoringEvaluationData> =>
  apiRequest(
    `/api/v1/monitoring-samples/${encodeURIComponent(sampleId)}/evaluation`,
    { method: "PUT", body: JSON.stringify(input) },
  );

export const getMonitoringMetrics = (
  clientId: string,
  from: string,
  to: string,
): Promise<MonitoringMetricsData> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/monitoring-metrics?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
  );

export const getOptimizationActions = (
  clientId: string,
): Promise<{ items: OptimizationActionData[] }> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/optimization-actions`,
  );

export const createMonitoringFeedback = (
  evaluationId: string,
  input: {
    action_type:
      | "add_fact_task"
      | "add_content_brief"
      | "update_channel_priority"
      | "increase_sample";
    reason: string;
    target_page: "P02" | "P04" | "P06" | "P07";
  },
): Promise<{
  id: string;
  action_type: string;
  target_level: string;
  target_page: string;
  converted_record_type: "optimization_action";
  converted_record_id: string;
  status: "open";
}> =>
  apiRequest(
    `/api/v1/monitoring-evaluations/${encodeURIComponent(evaluationId)}/feedback`,
    { method: "POST", body: JSON.stringify(input) },
  );
