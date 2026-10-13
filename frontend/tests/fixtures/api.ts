import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const apiRequests: URL[] = [];

const REQUEST_ID = "00000000-0000-4000-8000-000000000001";

export const successResponse = <T>(data: T, code: 200 | 201 | 202 = 200) => ({
  code,
  message: code === 201 ? "created" : code === 202 ? "accepted" : "success",
  data,
  request_id: REQUEST_ID,
});

export const errorResponse = (
  code: number,
  message: string,
  fieldErrors: { field: string; message: string }[] = [],
) => ({
  code,
  message,
  data: {
    field_errors: fieldErrors,
    retryable: false,
    provider: null,
    job_id: null,
  },
  request_id: REQUEST_ID,
});

export const server = setupServer(
  http.get("/api/v1/auth/session", () =>
    HttpResponse.json(errorResponse(40101, "登录已失效，请重新登录"), {
      status: 401,
    }),
  ),
);

server.events.on("request:start", ({ request }) => {
  apiRequests.push(new URL(request.url));
});

export const session = {
  user: {
    id: "00000000-0000-4000-8000-000000000010",
    username: "owner",
    display_name: "平台负责人",
  },
  csrf_token: "mock-csrf-token",
  expires_at: "2026-07-28T00:00:00Z",
};

export const clientSummary = {
  id: "00000000-0000-4000-8000-000000000101",
  standard_name: "莱恩美术",
  short_name: "莱恩",
  industry_code: "art_education",
  industry_name: "少儿美术",
  province: "北京市",
  city: "北京市",
  district: "朝阳区",
  status: "active",
  current_level: "L1",
  fact_completeness: 60,
  blocking_issue_count: 2,
  next_action: "补充服务范围",
  updated_at: "2026-07-27T00:00:00Z",
  version: 1,
};

export const client = {
  ...clientSummary,
  address: "望京路 1 号",
  contact_phone: null,
  contact_wechat: null,
  business_hours: null,
  service_radius: null,
  cooperation_started_on: "2026-01-01",
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
};

export const secondClient = {
  ...clientSummary,
  id: "00000000-0000-4000-8000-000000000102",
  standard_name: "安心家政",
  short_name: "安心",
  industry_code: "housekeeping",
  industry_name: "家政服务",
};

export const clientsPage = (items = [clientSummary, secondClient]) =>
  successResponse({
    items,
    page: 1,
    page_size: 20,
    total: items.length,
    has_next: false,
  });

export const dashboard = () =>
  successResponse({
    client: clientSummary,
    counts: {
      materials: 3,
      confirmed_facts: 3,
      unresolved_conflicts: 0,
      planned_contents: 0,
      draft_contents: 0,
      monitoring_samples_30d: 0,
    },
    level_progress: {
      current: "L1",
      next: "L2",
      missing_conditions: ["补充服务范围"],
    },
    next_actions: [
      {
        id: "00000000-0000-4000-8000-000000000201",
        title: "补充服务范围",
        reason: "当前服务半径尚未确认",
        target_level: "L2",
        target_page: "P02",
        priority: 1,
      },
    ],
    recent_jobs: [],
  });
