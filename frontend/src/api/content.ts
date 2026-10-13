import { apiRequest } from "./http";
import type {
  ContentFormCode,
  ContentGenerationTaskData,
  ContentDocumentData,
  ContentStatus,
  DocumentVersionData,
  JobData,
  QualityCheckData,
} from "./dto";

interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

const getDocumentPage = (
  clientId: string,
  page: number,
  status?: ContentStatus,
): Promise<Page<ContentDocumentData>> => {
  const query = new URLSearchParams({ page: String(page), page_size: "100" });
  if (status) query.set("status", status);
  return apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/documents?${query}`,
  );
};

export const getDocuments = async (
  clientId: string,
  status?: ContentStatus,
): Promise<Page<ContentDocumentData>> => {
  const first = await getDocumentPage(clientId, 1, status);
  const items = [...first.items];
  const pageCount = Math.ceil(first.total / first.page_size);
  for (let page = 2; page <= pageCount; page += 1) {
    const next = await getDocumentPage(clientId, page, status);
    items.push(...next.items);
  }
  return {
    items,
    page: 1,
    page_size: items.length,
    total: first.total,
  };
};

export const createDocument = (
  clientId: string,
  input: { brief_id: string; title: string },
): Promise<ContentDocumentData> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}/documents`, {
    method: "POST",
    body: JSON.stringify(input),
  });

export const createDocumentBatch = (
  clientId: string,
  input: {
    keyword_ids: string[];
    platform_type: "self_media";
    article_count: number;
    length: "short" | "medium" | "long";
    style: "auto" | "guide" | "faq" | "service" | "scenario";
    content_form?: ContentFormCode | "smart_mix";
    content_form_codes: ContentFormCode[];
    target_channel_ids: string[];
  },
): Promise<{
  task: ContentGenerationTaskData;
  items: ContentDocumentData[];
  total: number;
}> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/documents/batch`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );

export const getContentGenerationTasks = (
  clientId: string,
): Promise<Page<ContentGenerationTaskData>> =>
  apiRequest(
    `/api/v1/clients/${encodeURIComponent(clientId)}/content-generation-tasks?page=1&page_size=100`,
  );

export const getContentGenerationTask = (
  taskId: string,
): Promise<ContentGenerationTaskData> =>
  apiRequest(`/api/v1/content-generation-tasks/${encodeURIComponent(taskId)}`);

export const confirmContentGenerationTask = (
  taskId: string,
  version: number,
): Promise<ContentGenerationTaskData> =>
  apiRequest(
    `/api/v1/content-generation-tasks/${encodeURIComponent(taskId)}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ version }),
    },
  );

export const getDocument = (documentId: string): Promise<ContentDocumentData> =>
  apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}`);

export const saveDocument = (
  documentId: string,
  input: {
    version: number;
    title: string;
    body_markdown: string;
    save_reason: string;
    source_version_id?: string;
    channel_id?: string;
  },
): Promise<ContentDocumentData> =>
  apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });

export const publishDocument = (
  documentId: string,
  version: number,
  accountIds: string[],
  idempotencyKey: string,
): Promise<{
  items: Array<{
    job_id: string;
    status: JobData["status"];
    progress: number;
    account_id: string;
    account_name: string;
    channel_id: string;
  }>;
  queued_count: number;
}> =>
  apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/publish`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, account_ids: accountIds }),
  });

export const deleteDocument = (
  documentId: string,
  version: number,
): Promise<ContentDocumentData> =>
  apiRequest(
    `/api/v1/documents/${encodeURIComponent(documentId)}?${new URLSearchParams({
      version: String(version),
    })}`,
    { method: "DELETE" },
  );

export const restoreDocument = (
  documentId: string,
  version: number,
): Promise<ContentDocumentData> =>
  apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/restore`, {
    method: "POST",
    body: JSON.stringify({ version }),
  });

export const runDocumentOperation = (
  documentId: string,
  idempotencyKey: string,
  input:
    | {
        operation: "check";
        source_version_id: string;
      }
    | {
        operation: "geo_optimize";
        source_version_id: string;
        target_question_ids: string[];
      }
    | {
        operation: "naturalize";
        source_version_id: string;
        content_type: string;
        intensity: "light" | "standard";
      }
    | {
        operation: "channel_variant";
        source_version_id: string;
        channel_ids: string[];
      }
    | {
        operation: "regenerate";
        source_version_id: string;
        revision_instruction: string;
        target_channel_id: string | null;
      }
    | {
        operation: "export";
        source_version_id: string;
        format: "markdown" | "docx";
        include_sources: boolean;
      },
): Promise<Pick<JobData, "id" | "status" | "progress"> & { job_id: string }> =>
  apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/operations`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  });

export const getDocumentVersions = (
  documentId: string,
): Promise<Page<DocumentVersionData>> =>
  apiRequest(
    `/api/v1/documents/${encodeURIComponent(documentId)}/versions?page=1&page_size=100`,
  );

export const restoreDocumentVersion = (
  documentId: string,
  versionId: string,
  input: { document_version: number; reason: string },
): Promise<ContentDocumentData> =>
  apiRequest(
    `/api/v1/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/restore`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );

export const getDocumentChecks = (
  documentId: string,
): Promise<Page<QualityCheckData>> =>
  apiRequest(
    `/api/v1/documents/${encodeURIComponent(documentId)}/quality-checks?page=1&page_size=100`,
  );

export const exportDownloadUrl = (exportId: string): string =>
  `/api/v1/exports/${encodeURIComponent(exportId)}/download`;
