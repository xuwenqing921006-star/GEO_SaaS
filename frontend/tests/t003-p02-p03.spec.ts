import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { createPinia } from "pinia";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";
import { http, HttpResponse } from "msw";

import App from "../src/App.vue";
import type { ClientSummary } from "../src/api/dto";
import { router } from "../src/router";
import { useSessionStore } from "../src/stores/session";
import { useWorkspaceStore } from "../src/stores/workspace";
import {
  clientSummary,
  server,
  session,
  successResponse,
} from "./fixtures/api";

const profile = {
  client_id: clientSummary.id,
  services: [],
  capabilities: [],
  prohibited_claims: [
    {
      id: "claim",
      phrase: "保证提升",
      reason: "缺少可验证依据",
      source: "system" as const,
    },
  ],
  external_presences: [],
  missing_questions: [
    {
      id: "audience",
      field_key: "audience",
      question: "请确认适合人群",
      reason: "用于场景问题",
      blocking: false,
    },
  ],
  version: 1,
};
const facts = [
  {
    id: "fact-service",
    client_id: clientSummary.id,
    category: "service",
    key: "core_service",
    label: "核心服务",
    value: "少儿美术培训与创作课程",
    status: "confirmed",
    confidence: 92,
    valid_from: null,
    valid_until: null,
    evidence: [
      {
        id: "evidence-service",
        material_id: null,
        source_type: "manual",
        source_label: "客户确认",
        source_url: null,
        quote: "提供少儿美术培训与创作课程。",
        observed_at: "2026-07-20",
        authorization_status: "authorized",
      },
    ],
    version: 1,
    updated_at: "2026-07-20T08:00:00Z",
  },
];
const diagnostic = {
  id: "run-1",
  client_id: clientSummary.id,
  status: "succeeded",
  current_level: "L1",
  scores: {
    entity_completeness: 60,
    evidence_coverage: 55,
    content_coverage: 20,
    source_coverage: 15,
    ai_visibility: 0,
  },
  scope: ["entity", "evidence", "content", "source", "visibility"],
  monitoring_window_days: 30,
  overall_score: 72,
  overall_grade: "good",
  evaluated_platform_count: 1,
  total_platform_count: 3,
  effective_sample_count: 4,
  platform_results: [
    {
      platform_id: "deepseek",
      platform_name: "DeepSeek",
      collection_mode: "api",
      status: "associated",
      score: 72,
      grade: "good",
      comment: "能够正确关联企业与主营服务，但推荐出现率仍需提升。",
      valid_sample_count: 4,
      measured_at: "2026-07-25T09:30:00Z",
      metrics: {
        mention_rate: 0.75,
        association_rate: 0.75,
        recommendation_rate: 0.5,
        accuracy_rate: 1,
        stability_rate: 0.6,
      },
    },
  ],
  issues: [
    {
      id: "issue-1",
      category: "entity",
      severity: "blocking",
      title: "服务范围尚未确认",
      explanation: "地区 + 服务边界不完整。",
      evidence_ids: ["evidence-service"],
      suggested_action: "确认服务范围。",
      target_page: "P02",
      status: "open",
      version: 1,
    },
  ],
  fact_snapshot_id: "snapshot-1",
  is_stale: false,
  changed_fact_count: 0,
  completed_at: "2026-07-25T10:00:00Z",
};

const renderOwnerPage = async (path: string) => {
  const pinia = createPinia();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useSessionStore(pinia).setSession(session);
  useWorkspaceStore(pinia).setCurrentClient(clientSummary as ClientSummary);
  await router.replace(path);
  await router.isReady();
  render(App, {
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] },
  });
};

describe("T-003 P02/P03 Mock", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  beforeEach(() => {
    server.use(
      http.get("/api/v1/clients/:clientId", ({ params }) =>
        HttpResponse.json(
          successResponse({
            ...clientSummary,
            id: String(params.clientId),
            address: "测试地址",
            contact_phone: null,
            contact_wechat: null,
            business_hours: null,
            service_radius: null,
            cooperation_started_on: "2026-01-01",
            notes: null,
            created_at: "2026-01-01T00:00:00Z",
          }),
        ),
      ),
      http.get(`/api/v1/clients/${clientSummary.id}/materials`, () =>
        HttpResponse.json(successResponse({ items: [] })),
      ),
      http.get(`/api/v1/clients/${clientSummary.id}/facts`, () =>
        HttpResponse.json(successResponse({ items: facts })),
      ),
      http.get(`/api/v1/clients/${clientSummary.id}/conflicts`, () =>
        HttpResponse.json(successResponse({ items: [] })),
      ),
      http.get(`/api/v1/clients/${clientSummary.id}/knowledge-profile`, () =>
        HttpResponse.json(successResponse(profile)),
      ),
      http.get(`/api/v1/clients/${clientSummary.id}/diagnostics/latest`, () =>
        HttpResponse.json(successResponse(diagnostic)),
      ),
    );
  });
  afterEach(async () => {
    cleanup();
    server.resetHandlers();
    await router.replace("/login");
  });
  afterAll(() => server.close());

  it("presents the knowledge base as direct-entry management with a downloadable template", async () => {
    await renderOwnerPage(`/knowledge?clientId=${clientSummary.id}`);
    expect(
      await screen.findByRole("heading", { name: "企业知识库" }),
    ).toBeTruthy();
    expect(
      await screen.findByRole("heading", { name: "资料导入" }),
    ).toBeTruthy();
    const templateLinks = screen.getAllByRole("link", {
      name: "下载客户资料模板",
    });
    expect(templateLinks).toHaveLength(1);
    expect(
      templateLinks.every(
        (link) =>
          link.getAttribute("href") === "/downloads/GEO客户资料采集表模板.xlsx",
      ),
    ).toBe(true);
    expect(await screen.findByText("核心服务")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "编辑核心服务" }));
    const dialog = await screen.findByRole("dialog", { name: "编辑知识条目" });
    expect(dialog).toBeTruthy();
    expect(screen.getByDisplayValue("少儿美术培训与创作课程")).toBeTruthy();
    expect(screen.queryByText("公开授权")).toBeNull();
    expect(screen.queryByText("资料冲突")).toBeNull();
  });

  it("shows platform visibility scores and actionable GEO advice", async () => {
    await renderOwnerPage(`/diagnostics?clientId=${clientSummary.id}`);
    expect(
      await screen.findByRole("heading", { name: "GEO 诊断" }),
    ).toBeTruthy();
    expect(await screen.findByText("AI 平台收录与推荐表现")).toBeTruthy();
    expect(screen.getByText("DeepSeek")).toBeTruthy();
    expect(screen.getByText("正确关联")).toBeTruthy();
    expect(screen.getByText("服务范围尚未确认")).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成关键词" })).toBeTruthy();
  });

  it("marks a diagnostic as historical after enterprise knowledge changes", async () => {
    server.use(
      http.get(`/api/v1/clients/${clientSummary.id}/diagnostics/latest`, () =>
        HttpResponse.json(
          successResponse({
            ...diagnostic,
            is_stale: true,
            changed_fact_count: 3,
          }),
        ),
      ),
    );

    await renderOwnerPage(`/diagnostics?clientId=${clientSummary.id}`);
    expect(await screen.findByText("企业知识库已经更新")).toBeTruthy();
    expect(screen.getByText(/已有 3 项信息变化/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "立即更新诊断" })).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "生成关键词" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });

  it("does not disguise a missing core fact as a successful diagnostic", async () => {
    const incompleteClientId = "00000000-0000-4000-8000-000000000102";
    server.use(
      http.get(`/api/v1/clients/${incompleteClientId}/knowledge-profile`, () =>
        HttpResponse.json(
          successResponse({
            ...profile,
            client_id: incompleteClientId,
            missing_questions: [
              {
                id: "missing-core-service",
                field_key: "core_service",
                question: "请先补充客户的核心服务。",
                reason: "没有服务事实不能生成可靠诊断。",
                blocking: true,
              },
            ],
          }),
        ),
      ),
      http.get(`/api/v1/clients/${incompleteClientId}/diagnostics/latest`, () =>
        HttpResponse.json(successResponse(null)),
      ),
    );

    await renderOwnerPage(`/diagnostics?clientId=${incompleteClientId}`);
    expect(await screen.findByText("还没有 GEO 诊断结果")).toBeTruthy();
    expect(screen.getByRole("button", { name: "开始首次诊断" })).toBeTruthy();
  });

  it("does not show stale scores when the latest diagnostic failed", async () => {
    server.use(
      http.get(`/api/v1/clients/${clientSummary.id}/diagnostics/latest`, () =>
        HttpResponse.json(successResponse({ ...diagnostic, status: "failed" })),
      ),
    );

    await renderOwnerPage(`/diagnostics?clientId=${clientSummary.id}`);
    expect(await screen.findByText("上一次诊断未完成")).toBeTruthy();
    expect(screen.queryByText("综合评分")).toBeNull();
  });

  it("keeps a knowledge-base API failure visibly recoverable", async () => {
    server.use(
      http.get(`/api/v1/clients/${clientSummary.id}/facts`, () =>
        HttpResponse.json({ message: "暂时不可用" }, { status: 503 }),
      ),
    );

    await renderOwnerPage(`/knowledge?clientId=${clientSummary.id}`);
    expect(await screen.findByText("企业知识库暂时无法载入")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新载入" })).toBeTruthy();
  });

  it("clears the knowledge editor when switching to another client", async () => {
    const secondClientId = "00000000-0000-4000-8000-000000000102";
    server.use(
      http.get(`/api/v1/clients/${secondClientId}/materials`, () =>
        HttpResponse.json(successResponse({ items: [] })),
      ),
      http.get(`/api/v1/clients/${secondClientId}/facts`, () =>
        HttpResponse.json(successResponse({ items: [] })),
      ),
      http.get(`/api/v1/clients/${secondClientId}/conflicts`, () =>
        HttpResponse.json(successResponse({ items: [] })),
      ),
      http.get(`/api/v1/clients/${secondClientId}/knowledge-profile`, () =>
        HttpResponse.json(
          successResponse({ ...profile, client_id: secondClientId }),
        ),
      ),
    );

    await renderOwnerPage(`/knowledge?clientId=${clientSummary.id}`);
    await fireEvent.click(
      await screen.findByRole("button", { name: "编辑核心服务" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "编辑知识条目" }),
    ).toBeTruthy();

    await router.replace(`/knowledge?clientId=${secondClientId}`);
    expect(await screen.findByText("还没有知识条目")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "编辑知识条目" })).toBeNull();
  });
});
