import type { ContentDocumentData } from "./api/dto";

export interface ContentGenerationState {
  selectedKeywordCount: number;
  diagnosticStale: boolean;
  strategyOutdated: boolean;
  contentFormTemplateCount: number;
  promptsPending: boolean;
  channelsPending: boolean;
  batchPending: boolean;
}

export interface ContentGenerationAvailability {
  enabled: boolean;
  reason: string;
}

export interface ContentDocumentFilters {
  keyword: string;
  keywordType: string;
  generation: string;
  publication: string;
  channelId: string;
}

export type PublicationBucket = "unpublished" | "published" | "failed";

export interface PublicationDocumentFilters {
  bucket: PublicationBucket;
  keyword: string;
  keywordType: string;
  channelId: string;
}

export const plannedContentCount = (
  articleCountPerPlatform: number,
  selectedPlatformCount: number,
): number =>
  Math.max(1, Math.min(20, Number(articleCountPerPlatform) || 1)) *
  Math.max(0, selectedPlatformCount);

export const toggleAllKeywordSelection = (
  keywordIds: string[],
  selectedKeywordIds: string[],
  limit = 20,
): string[] => {
  const selectableIds = [...new Set(keywordIds)].slice(0, limit);
  const selectedIds = new Set(selectedKeywordIds);
  const isAllSelected =
    selectableIds.length > 0 &&
    selectableIds.every((id) => selectedIds.has(id));
  return isAllSelected ? [] : selectableIds;
};

export const contentGenerationAvailability = (
  state: ContentGenerationState,
): ContentGenerationAvailability => {
  if (state.selectedKeywordCount === 0)
    return { enabled: false, reason: "请先选择关键词" };
  if (state.diagnosticStale)
    return {
      enabled: false,
      reason: "企业资料已经更新，请先重新运行 GEO 诊断",
    };
  if (state.promptsPending || state.channelsPending)
    return { enabled: false, reason: "正在载入内容模板与渠道规则" };
  if (state.contentFormTemplateCount === 0)
    return { enabled: false, reason: "内容形式尚未配置" };
  if (state.batchPending) return { enabled: false, reason: "文章任务正在创建" };
  return { enabled: true, reason: "" };
};

export const documentChannelIds = (document: ContentDocumentData): string[] => {
  const adaptedChannelId = document.current_version?.target_channel_id;
  const variants = document.channel_variants.map((item) => item.channel_id);
  const ids = adaptedChannelId ? [adaptedChannelId, ...variants] : variants;
  return [...new Set(ids)];
};

export const documentPublishableChannelIds = (
  document: ContentDocumentData,
): string[] => {
  const adaptedChannelId = document.current_version?.target_channel_id;
  return [
    ...new Set([
      ...(adaptedChannelId ? [adaptedChannelId] : []),
      ...document.channel_variants.map((item) => item.channel_id),
    ]),
  ];
};

const generationMatches = (
  document: ContentDocumentData,
  generation: string,
): boolean => {
  if (generation === "all") return true;
  if (generation === "ready")
    return (
      document.generation_status === "generated" &&
      document.status !== "blocked" &&
      document.latest_check?.overall_status !== "blocked"
    );
  if (generation === "needs_attention")
    return (
      document.status === "blocked" ||
      document.latest_check?.overall_status === "blocked"
    );
  return document.generation_status === generation;
};

const publicationMatches = (
  document: ContentDocumentData,
  publication: string,
): boolean => {
  if (publication === "all") return true;
  if (publication === "published") return document.current_version_published;
  if (publication === "unpublished") return !document.current_version_published;
  return document.publication_status === publication;
};

export const filterContentDocuments = (
  documents: ContentDocumentData[],
  filters: ContentDocumentFilters,
): ContentDocumentData[] => {
  const keyword = filters.keyword.trim().toLocaleLowerCase("zh-CN");
  return documents.filter((document) => {
    const keywordMatches =
      !keyword ||
      `${document.keyword ?? ""} ${document.current_version?.title ?? document.title}`
        .toLocaleLowerCase("zh-CN")
        .includes(keyword);
    const typeMatches =
      filters.keywordType === "all" ||
      document.keyword_type === filters.keywordType;
    const channelMatches =
      filters.channelId === "all" ||
      documentChannelIds(document).includes(filters.channelId);
    return (
      keywordMatches &&
      typeMatches &&
      channelMatches &&
      generationMatches(document, filters.generation) &&
      publicationMatches(document, filters.publication)
    );
  });
};

export const publicationBucket = (
  document: ContentDocumentData,
): PublicationBucket => {
  if (
    ["failed", "needs_login", "needs_verification", "rejected"].includes(
      document.publication_status,
    )
  )
    return "failed";
  if (
    document.current_version_published ||
    document.publication_status === "published"
  )
    return "published";
  return "unpublished";
};

export const filterPublicationDocuments = (
  documents: ContentDocumentData[],
  filters: PublicationDocumentFilters,
): ContentDocumentData[] => {
  const keyword = filters.keyword.trim().toLocaleLowerCase("zh-CN");
  return documents.filter((document) => {
    if (!document.generation_task_confirmed_at) return false;
    if (!canRecordPublication(document)) return false;
    if (publicationBucket(document) !== filters.bucket) return false;
    const keywordMatches =
      !keyword ||
      `${document.keyword ?? ""} ${document.current_version?.title ?? document.title}`
        .toLocaleLowerCase("zh-CN")
        .includes(keyword);
    const typeMatches =
      filters.keywordType === "all" ||
      document.keyword_type === filters.keywordType;
    const channelMatches =
      filters.channelId === "all" ||
      documentChannelIds(document).includes(filters.channelId);
    return keywordMatches && typeMatches && channelMatches;
  });
};

export const canRecordPublication = (document: ContentDocumentData): boolean =>
  Boolean(document.current_version) &&
  document.generation_status === "generated" &&
  document.status !== "blocked" &&
  document.latest_check?.overall_status !== "blocked" &&
  document.status !== "archived" &&
  documentPublishableChannelIds(document).length > 0;

export const shouldPollContentDocuments = (
  documents: ContentDocumentData[] | undefined,
): boolean => contentDocumentsRefetchInterval(documents) !== false;

export const contentDocumentsRefetchInterval = (
  documents: ContentDocumentData[] | undefined,
): number | false => {
  if (
    documents?.some(
      (document) =>
        ["pending", "generating"].includes(document.generation_status) ||
        ["queued", "publishing"].includes(document.publication_status),
    )
  )
    return 5_000;
  if (
    documents?.some(
      (document) => document.publication_status === "pending_review",
    )
  )
    return 60_000;
  return false;
};
