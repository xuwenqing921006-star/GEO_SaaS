import { describe, expect, it } from "vitest";
import type { ContentDocumentData } from "../src/api/dto";
import {
  canRecordPublication,
  contentDocumentsRefetchInterval,
  contentGenerationAvailability,
  filterContentDocuments,
  filterPublicationDocuments,
  plannedContentCount,
  publicationBucket,
  shouldPollContentDocuments,
  toggleAllKeywordSelection,
} from "../src/contentWorkbenchLogic";

const document = (
  overrides: Partial<ContentDocumentData>,
): ContentDocumentData =>
  ({
    id: "document-1",
    client_id: "client-1",
    brief_id: "brief-1",
    generation_task_id: "task-1",
    generation_task_confirmed_at: "2026-07-29T00:00:00Z",
    title: "即墨少儿美术课程怎么选",
    status: "checked",
    generation_status: "generated",
    publication_status: "unpublished",
    publication_error: null,
    keyword: "即墨少儿美术机构",
    keyword_type: "local_service",
    current_version: {
      id: "version-1",
      document_id: "document-1",
      version_number: 1,
      title: "即墨少儿美术课程怎么选",
      body_markdown: "正文",
      change_type: "generated",
      provider: "qwen",
      model: "qwen",
      fact_snapshot_id: "snapshot-1",
      prompt_version: "content-v2",
      prompt_template_code: "selection_guide",
      prompt_template_version: 1,
      target_channel_id: "toutiao",
      contact_policy: "omit",
      prompt_layers_snapshot: [],
      image_material_ids: [],
      input_tokens: 0,
      output_tokens: 0,
      fallback_reason: null,
      created_at: "2026-07-29T00:00:00Z",
    },
    latest_check: null,
    fact_snapshot: {
      id: "snapshot-1",
      brief_version: 1,
      facts: [],
      evidence: [],
      brief_context: {
        title: "即墨少儿美术课程怎么选",
        content_type: "selection_guide",
        target_keywords: ["即墨少儿美术"],
        retest_questions: ["即墨少儿美术机构"],
        target_level: "L1",
        audience: "家长",
        angle: "选择指南",
        suggested_channel_ids: ["sohu", "baijia"],
        expected_recommendation_reason: "真实信息",
      },
      created_at: "2026-07-29T00:00:00Z",
    },
    channel_variants: [],
    latest_publication: null,
    current_version_published: false,
    updated_at: "2026-07-29T00:00:00Z",
    version: 1,
    ...overrides,
  }) as ContentDocumentData;

describe("content workbench logic", () => {
  it("按每个平台篇数计算任务总量，不再乘以关键词数量", () => {
    expect(plannedContentCount(5, 4)).toBe(20);
    expect(plannedContentCount(5, 0)).toBe(0);
    expect(plannedContentCount(50, 2)).toBe(40);
  });

  it("关键词全选遵守 20 个上限，并可一键取消全选", () => {
    const keywordIds = Array.from(
      { length: 25 },
      (_, index) => `keyword-${index}`,
    );
    const selected = toggleAllKeywordSelection(keywordIds, []);

    expect(selected).toEqual(keywordIds.slice(0, 20));
    expect(toggleAllKeywordSelection(keywordIds, selected)).toEqual([]);
  });

  it("只在存在等待生成或生成中文章时轮询列表", () => {
    expect(shouldPollContentDocuments(undefined)).toBe(false);
    expect(
      shouldPollContentDocuments([
        document({ status: "checked" }),
        document({
          id: "failed",
          status: "failed",
          generation_status: "failed",
        }),
      ]),
    ).toBe(false);
    expect(
      shouldPollContentDocuments([
        document({ status: "checked" }),
        document({
          id: "generating",
          status: "generating",
          generation_status: "generating",
        }),
      ]),
    ).toBe(true);
    expect(
      shouldPollContentDocuments([
        document({
          id: "brief",
          status: "brief",
          generation_status: "pending",
        }),
      ]),
    ).toBe(true);
  });

  it("发布中快速刷新，平台审核中改为低频复查", () => {
    expect(
      contentDocumentsRefetchInterval([
        document({ publication_status: "publishing" }),
      ]),
    ).toBe(5_000);
    expect(
      contentDocumentsRefetchInterval([
        document({ publication_status: "pending_review" }),
      ]),
    ).toBe(60_000);
    expect(contentDocumentsRefetchInterval([document({})])).toBe(false);
  });

  it("allows an explicitly selected keyword even when its strategy predates the latest diagnostic", () => {
    expect(
      contentGenerationAvailability({
        selectedKeywordCount: 1,
        diagnosticStale: false,
        strategyOutdated: true,
        contentFormTemplateCount: 3,
        promptsPending: false,
        channelsPending: false,
        batchPending: false,
      }),
    ).toEqual({ enabled: true, reason: "" });
  });

  it("explains the real reason when generation is unavailable", () => {
    expect(
      contentGenerationAvailability({
        selectedKeywordCount: 0,
        diagnosticStale: false,
        strategyOutdated: false,
        contentFormTemplateCount: 3,
        promptsPending: false,
        channelsPending: false,
        batchPending: false,
      }).reason,
    ).toContain("选择关键词");
  });

  it("filters by keyword, type, publication state and suitable channel", () => {
    const blocked = document({
      id: "document-2",
      status: "blocked",
      keyword: "莱恩美术怎么样",
      keyword_type: "brand",
      current_version: {
        ...document({}).current_version!,
        id: "version-2",
        document_id: "document-2",
        target_channel_id: null,
      },
      fact_snapshot: {
        ...document({}).fact_snapshot!,
        brief_context: {
          ...document({}).fact_snapshot!.brief_context,
          suggested_channel_ids: ["zhihu"],
        },
      },
      channel_variants: [
        {
          id: "variant-zhihu",
          channel_id: "zhihu",
          version_id: "version-2",
          adaptation_note: "已按知乎规则生成",
        },
      ],
    });
    const published = document({
      status: "published",
      publication_status: "published",
      latest_publication: {
        id: "publication-1",
        document_version_id: "version-1",
        channel_id: "toutiao",
        status: "published",
        public_url: "https://www.toutiao.com/article/1",
        error_message: null,
        submitted_at: "2026-07-29T00:00:00Z",
        published_at: "2026-07-29T00:00:00Z",
      },
      current_version_published: true,
    });

    expect(
      filterContentDocuments([blocked, published], {
        keyword: "少儿美术",
        keywordType: "local_service",
        generation: "all",
        publication: "published",
        channelId: "toutiao",
      }).map((item) => item.id),
    ).toEqual(["document-1"]);
    expect(
      filterContentDocuments([blocked, published], {
        keyword: "",
        keywordType: "all",
        generation: "generated",
        publication: "unpublished",
        channelId: "zhihu",
      }).map((item) => item.id),
    ).toEqual(["document-2"]);
  });

  it("treats a generated target channel as adapted instead of mixing planned channels", () => {
    expect(
      filterContentDocuments([document({})], {
        keyword: "",
        keywordType: "all",
        generation: "all",
        publication: "all",
        channelId: "baijia",
      }),
    ).toEqual([]);
  });

  it("blocks publication until the current article passes automatic quality checks", () => {
    expect(canRecordPublication(document({ status: "blocked" }))).toBe(false);
    expect(
      canRecordPublication(
        document({
          status: "checked",
          latest_check: {
            id: "check-blocked",
            document_version_id: "version-1",
            overall_status: "blocked",
            dimensions: [],
            findings: [],
            provider: "rules",
            model: "quality-rules",
            created_at: "2026-07-29T00:00:00Z",
          },
        }),
      ),
    ).toBe(false);
    expect(canRecordPublication(document({ status: "checked" }))).toBe(true);
    expect(
      canRecordPublication(
        document({
          status: "generating",
          generation_status: "generating",
          current_version: null,
        }),
      ),
    ).toBe(false);
  });

  it("keeps publication filtering after a published article is edited again", () => {
    const editedAfterPublication = document({
      status: "blocked",
      latest_publication: {
        id: "publication-1",
        document_version_id: "version-0",
        channel_id: "sohu",
        status: "published",
        public_url: "https://mp.sohu.com/article/1",
        error_message: null,
        submitted_at: "2026-07-29T00:00:00Z",
        published_at: "2026-07-29T00:00:00Z",
      },
      current_version_published: false,
    });
    expect(
      filterContentDocuments([editedAfterPublication], {
        keyword: "",
        keywordType: "all",
        generation: "all",
        publication: "published",
        channelId: "all",
      }),
    ).toHaveLength(0);
    expect(canRecordPublication(editedAfterPublication)).toBe(false);
  });

  it("filters generation failures and publication failures independently", () => {
    const generationFailed = document({
      id: "generation-failed",
      generation_status: "failed",
    });
    const publicationFailed = document({
      id: "publication-failed",
      publication_status: "failed",
    });

    expect(
      filterContentDocuments([generationFailed, publicationFailed], {
        keyword: "",
        keywordType: "all",
        generation: "failed",
        publication: "all",
        channelId: "all",
      }).map((item) => item.id),
    ).toEqual(["generation-failed"]);
    expect(
      filterContentDocuments([generationFailed, publicationFailed], {
        keyword: "",
        keywordType: "all",
        generation: "all",
        publication: "failed",
        channelId: "all",
      }).map((item) => item.id),
    ).toEqual(["publication-failed"]);
  });

  it("publishing workspace only exposes confirmed and publishable articles", () => {
    const unconfirmed = document({
      id: "unconfirmed",
      generation_task_confirmed_at: null,
    });
    const blocked = document({ id: "blocked", status: "blocked" });
    const ready = document({ id: "ready" });

    expect(
      filterPublicationDocuments([unconfirmed, blocked, ready], {
        bucket: "unpublished",
        keyword: "",
        keywordType: "all",
        channelId: "all",
      }).map((item) => item.id),
    ).toEqual(["ready"]);
  });

  it("routes confirmed articles into unpublished, published and failed tabs", () => {
    const unpublished = document({ id: "unpublished" });
    const published = document({
      id: "published",
      publication_status: "published",
      current_version_published: true,
    });
    const failed = document({
      id: "failed",
      publication_status: "needs_login",
    });

    expect(publicationBucket(unpublished)).toBe("unpublished");
    expect(publicationBucket(published)).toBe("published");
    expect(publicationBucket(failed)).toBe("failed");
    expect(
      filterPublicationDocuments([unpublished, published, failed], {
        bucket: "failed",
        keyword: "",
        keywordType: "all",
        channelId: "all",
      }).map((item) => item.id),
    ).toEqual(["failed"]);
  });
});
