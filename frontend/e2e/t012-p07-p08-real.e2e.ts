import { expect, test, type APIRequestContext } from "@playwright/test";

test.setTimeout(60_000);

const waitForJob = async (
  request: APIRequestContext,
  jobId: string,
): Promise<void> => {
  await expect
    .poll(
      async () => {
        const response = await request.get(`/api/v1/jobs/${jobId}`);
        return (await response.json()).data.status;
      },
      { timeout: 15_000 },
    )
    .toBe("succeeded");
};

const confirmFact = async (
  request: APIRequestContext,
  csrfToken: string,
  clientId: string,
  input: {
    category: "service" | "audience" | "location";
    key: string;
    label: string;
    value: string;
  },
): Promise<void> => {
  const headers = { "X-CSRF-Token": csrfToken };
  const created = await request.post(`/api/v1/clients/${clientId}/facts`, {
    headers,
    data: {
      ...input,
      status: "client_provided",
      valid_from: null,
      valid_until: null,
      evidence_ids: [],
    },
  });
  expect(created.status()).toBe(201);
  const fact = (await created.json()).data;
  const evidence = await request.post(`/api/v1/facts/${fact.id}/evidence`, {
    headers,
    data: {
      source_type: "manual",
      material_id: null,
      source_label: "客户资料与负责人核验",
      source_url: null,
      quote: input.value,
      observed_at: "2026-07-28",
      authorization_status: "authorized",
    },
  });
  expect(evidence.status()).toBe(201);
  const withEvidence = (await evidence.json()).data;
  const confirmed = await request.post(`/api/v1/facts/${fact.id}/confirm`, {
    headers,
    data: {
      version: withEvidence.version,
      evidence_ids: [withEvidence.evidence[0].id],
      confirmation_note: "负责人确认可公开",
    },
  });
  expect(confirmed.status()).toBe(200);
};

test("real P07 separates API, manual, failed and unmentioned samples", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("CorrectPassword2026!");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/clients/);

  const session = await page.request.get("/api/v1/auth/session");
  const csrfToken = (await session.json()).data.csrf_token as string;
  const created = await page.request.post("/api/v1/clients", {
    headers: { "X-CSRF-Token": csrfToken },
    data: {
      standard_name: `莱恩美术 P07 ${Date.now()}`,
      short_name: "莱恩美术",
      industry_code: "art_education",
      industry_name: "少儿美术培训",
      province: "山东省",
      city: "青岛市",
      district: "即墨区",
      address: "即墨区测试地址",
      contact_phone: null,
      contact_wechat: null,
      business_hours: "09:00-18:00",
      service_radius: "即墨区",
      cooperation_started_on: "2026-07-28",
      notes: "T012 监测闭环验收客户",
    },
  });
  expect(created.status()).toBe(201);
  const clientId = (await created.json()).data.id as string;
  await confirmFact(page.request, csrfToken, clientId, {
    category: "service",
    key: "service.primary",
    label: "核心服务",
    value: "少儿美术培训",
  });
  await confirmFact(page.request, csrfToken, clientId, {
    category: "audience",
    key: "audience.primary",
    label: "适用客群",
    value: "即墨区儿童及家长",
  });
  await confirmFact(page.request, csrfToken, clientId, {
    category: "location",
    key: "location.service_area",
    label: "服务范围",
    value: "即墨区",
  });
  const diagnostic = await page.request.post(
    `/api/v1/clients/${clientId}/diagnostics`,
    {
      headers: {
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": crypto.randomUUID(),
      },
      data: {
        scope: ["entity", "evidence", "content", "source", "visibility"],
        monitoring_window_days: 30,
      },
    },
  );
  await waitForJob(page.request, (await diagnostic.json()).data.job_id);
  const latest = await page.request.get(
    `/api/v1/clients/${clientId}/diagnostics/latest`,
  );
  const strategyJob = await page.request.post(
    `/api/v1/clients/${clientId}/strategy/generate`,
    {
      headers: {
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": crypto.randomUUID(),
      },
      data: {
        diagnostic_run_id: (await latest.json()).data.id,
        include_families: [
          "discovery",
          "recommendation",
          "scenario",
          "comparison",
          "brand_verification",
        ],
        brief_count: 3,
      },
    },
  );
  await waitForJob(page.request, (await strategyJob.json()).data.job_id);
  const strategy = await page.request.get(
    `/api/v1/clients/${clientId}/strategy`,
  );
  const questionItems = (await strategy.json()).data.items.filter(
    (item: { kind: string }) => item.kind === "question",
  );
  for (const item of questionItems) {
    const locked = await page.request.patch(
      `/api/v1/strategy-items/${item.id}`,
      {
        headers: { "X-CSRF-Token": csrfToken },
        data: { version: item.version, locked: true },
      },
    );
    expect(locked.status()).toBe(200);
  }

  await page.goto(`/monitoring?clientId=${clientId}`);
  await expect(page).toHaveURL(
    new RegExp(`/diagnostics\\?clientId=${clientId}`),
  );
  await expect(
    page.getByRole("heading", { name: "GEO 诊断", level: 1 }),
  ).toBeVisible();
  await expect(page.locator(".platform-result-table tbody tr")).toHaveCount(4);
  await expect(page.locator(".diagnosis-probe-questions p")).toHaveCount(3);
  await expect(page.getByText("DeepSeek", { exact: true })).toBeVisible();
  await expect(page.getByText("通义千问", { exact: true })).toBeVisible();
  await expect(page.getByText("豆包", { exact: true })).toBeVisible();
  await expect(page.getByText("文心一言", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("人工采样");

  await page.goto(`/settings?clientId=${clientId}`);
  await expect(
    page.getByRole("heading", { name: "AI 引擎控制台" }),
  ).toBeVisible();
  await expect(
    page.getByText("DeepSeek", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("通义千问", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("豆包", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("文心一言", { exact: true }).first(),
  ).toBeVisible();
});
