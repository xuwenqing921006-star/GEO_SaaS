import { apiRequest } from "./http";
import type {
  AuthorizationStatus,
  ConflictData,
  DiagnosticRunData,
  FactData,
  KnowledgeProfileData,
  MaterialData,
} from "./dto";

interface PageData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

const listAllPages = async <T>(path: string): Promise<{ items: T[] }> => {
  const items: T[] = [];
  let page = 1;
  let hasNext = true;
  while (hasNext) {
    const separator = path.includes("?") ? "&" : "?";
    const result = await apiRequest<PageData<T>>(
      `${path}${separator}page=${page}&page_size=100`,
    );
    items.push(...result.items);
    hasNext = result.has_next;
    page += 1;
  }
  return { items };
};

export const listMaterials = (
  clientId: string,
): Promise<{ items: MaterialData[] }> =>
  listAllPages(`/api/v1/clients/${encodeURIComponent(clientId)}/materials`);

export const materialFileUrl = (materialId: string): string =>
  `/api/v1/materials/${encodeURIComponent(materialId)}/file`;

export const deleteMaterial = (
  materialId: string,
): Promise<{ id: string; deleted: true }> =>
  apiRequest(`/api/v1/materials/${encodeURIComponent(materialId)}`, {
    method: "DELETE",
  });

export const listFacts = (clientId: string): Promise<{ items: FactData[] }> =>
  listAllPages(`/api/v1/clients/${encodeURIComponent(clientId)}/facts`);

export const listConflicts = (
  clientId: string,
): Promise<{ items: ConflictData[] }> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/conflicts`);

export const getKnowledgeProfile = (
  clientId: string,
): Promise<KnowledgeProfileData> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/knowledge-profile`,
  );

export const updateKnowledgeProfile = (
  clientId: string,
  profile: Pick<
    KnowledgeProfileData,
    | "version"
    | "services"
    | "capabilities"
    | "prohibited_claims"
    | "external_presences"
  >,
): Promise<KnowledgeProfileData> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/knowledge-profile`,
    {
      method: "PATCH",
      body: JSON.stringify(profile),
    },
  );

export const getLatestDiagnostic = (
  clientId: string,
): Promise<DiagnosticRunData | null> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/diagnostics/latest`,
  );

export const uploadMaterials = (
  clientId: string,
  files: File[],
  category: MaterialData["category"],
  authorizationStatus: AuthorizationStatus,
): Promise<{ items: MaterialData[] }> => {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  form.append("category", category);
  form.append("authorization_status", authorizationStatus);
  return apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/materials`,
    { method: "POST", body: form },
  );
};

export const extractMaterial = (
  materialId: string,
  idempotencyKey: string,
): Promise<{
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  resource_type: "material";
  resource_id: string;
}> =>
  apiRequest(`/api/v1/materials/${encodeURIComponent(materialId)}/extract`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ force: false, languages: ["zh-CN"] }),
  });

export const createFact = (
  clientId: string,
  input: {
    category: FactData["category"];
    key: string;
    label: string;
    value: string;
    status: "client_provided" | "private";
  },
): Promise<FactData> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/facts`, {
    method: "POST",
    body: JSON.stringify({
      ...input,
      valid_from: null,
      valid_until: null,
      evidence_ids: [],
    }),
  });

export const updateFact = (
  factId: string,
  version: number,
  input: {
    label?: string;
    value?: string;
    status?: Exclude<FactData["status"], "confirmed">;
  },
): Promise<FactData> =>
  apiRequest(`/api/v1/facts/${encodeURIComponent(factId)}`, {
    method: "PATCH",
    body: JSON.stringify({ version, ...input }),
  });

export const addFactEvidence = (
  factId: string,
  input: {
    source_type: "material" | "manual";
    material_id: string | null;
    source_label: string;
    quote: string;
    authorization_status: AuthorizationStatus;
  },
): Promise<FactData> =>
  apiRequest(`/api/v1/facts/${encodeURIComponent(factId)}/evidence`, {
    method: "POST",
    body: JSON.stringify({
      source_url: null,
      observed_at: new Date().toISOString().slice(0, 10),
      ...input,
    }),
  });

export const confirmFact = (
  factId: string,
  version: number,
  evidenceIds: string[],
): Promise<FactData> =>
  apiRequest(`/api/v1/facts/${encodeURIComponent(factId)}/confirm`, {
    method: "POST",
    body: JSON.stringify({
      version,
      evidence_ids: evidenceIds,
      confirmation_note: "平台负责人核验并确认可公开",
    }),
  });

export const resolveConflict = (
  conflictId: string,
  input:
    | {
        version: number;
        action: "select";
        selected_evidence_id: string;
        manual_value: null;
        resolution_note: string;
      }
    | {
        version: number;
        action: "manual";
        selected_evidence_id: null;
        manual_value: string;
        resolution_note: string;
      }
    | {
        version: number;
        action: "ignore";
        selected_evidence_id: null;
        manual_value: null;
        resolution_note: string;
      },
): Promise<ConflictData> =>
  apiRequest(`/api/v1/conflicts/${encodeURIComponent(conflictId)}/resolve`, {
    method: "POST",
    body: JSON.stringify(input),
  });
