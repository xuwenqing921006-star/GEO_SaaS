import { expect, test, type APIRequestContext } from "@playwright/test";

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
  const withEvidence = await request.post(`/api/v1/facts/${fact.id}/evidence`, {
    headers,
    data: {
      source_type: "manual",
      material_id: null,
      source_label: "客户资料与负责人核验",
      source_url: null,
      quote: input.value,
      observed_at: "2026-07-27",
      authorization_status: "authorized",
    },
  });
  const factWithEvidence = (await withEvidence.json()).data;
  const confirmed = await request.post(`/api/v1/facts/${fact.id}/confirm`, {
    headers,
    data: {
      version: factWithEvidence.version,
      evidence_ids: [factWithEvidence.evidence[0].id],
      confirmation_note: "负责人确认可公开",
    },
  });
  expect(confirmed.status()).toBe(200);
};

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

test("real P05 creates, reviews and confirms a platform-ready article task", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("CorrectPassword2026!");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/clients/);

  const session = await page.request.get("/api/v1/auth/session");
  expect(session.status()).toBe(200);
  const csrfToken = (await session.json()).data.csrf_token as string;
  const created = await page.request.post("/api/v1/clients", {
    headers: { "X-CSRF-Token": csrfToken },
    data: {
      standard_name: "莱恩美术 P05",
      short_name: "莱恩美术",
      industry_code: "art_education",
      province: "山东省",
      city: "青岛市",
      district: "即墨区",
      address: "即墨区测试地址",
      contact_phone: null,
      contact_wechat: null,
      business_hours: "09:00-18:00",
      service_radius: "即墨区",
      cooperation_started_on: "2026-07-27",
      notes: "T010 真实内容浏览器验收客户",
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
    value: "即墨区 4—12 岁儿童及家长",
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
  const strategy = await page.request.post(
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
  await waitForJob(page.request, (await strategy.json()).data.job_id);

  const generatedStrategy = await page.request.get(
    `/api/v1/clients/${clientId}/strategy`,
  );
  const keyword = (await generatedStrategy.json()).data.items.find(
    (item: { kind: string }) => item.kind === "keyword",
  );
  expect(keyword).toBeTruthy();
  const selected = await page.request.patch(
    `/api/v1/strategy-items/${keyword.id}`,
    {
      headers: { "X-CSRF-Token": csrfToken },
      data: { version: keyword.version, selected: true },
    },
  );
  expect(selected.status()).toBe(200);

  const accountResponse = await page.request.post(
    "/api/v1/publishing/channels/toutiao/accounts",
    {
      headers: { "X-CSRF-Token": csrfToken },
      data: { display_name: "头条号 E2E 账号" },
    },
  );
  expect(accountResponse.status()).toBe(201);
  const account = (await accountResponse.json()).data;
  const testedAccountResponse = await page.request.post(
    `/api/v1/publishing/accounts/${account.id}/test`,
    { headers: { "X-CSRF-Token": csrfToken } },
  );
  expect(testedAccountResponse.status()).toBe(200);
  const testedAccount = (await testedAccountResponse.json()).data;
  const enabledAccount = await page.request.patch(
    `/api/v1/publishing/accounts/${account.id}`,
    {
      headers: { "X-CSRF-Token": csrfToken },
      data: { version: testedAccount.version, enabled: true },
    },
  );
  expect(enabledAccount.status()).toBe(200);

  await page.goto(`/content?clientId=${clientId}`);
  await expect(
    page.getByRole("heading", { name: "内容工作台", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "文章生成任务" }),
  ).toBeVisible();
  await page
    .locator(".keyword-choice-list label")
    .filter({ hasText: keyword.text })
    .getByRole("checkbox")
    .check();
  await page
    .locator(".generation-channel-grid label")
    .filter({ hasText: "头条号" })
    .getByRole("checkbox")
    .check();
  await page
    .locator(".content-form-picker label")
    .filter({ hasText: "选择指南" })
    .getByRole("checkbox")
    .check();
  await page.getByLabel("每个平台篇数").fill("1");
  await page.getByRole("button", { name: "开始 AI 生成" }).click();

  const taskRow = page.locator(".generation-task-table tbody tr").first();
  await expect(taskRow).toContainText("已生成", { timeout: 30_000 });
  await expect(taskRow).toContainText(keyword.text);
  await taskRow.getByRole("button", { name: "查看" }).click();

  const taskDialog = page.getByRole("dialog", { name: "本次生成的文章" });
  const articleRow = taskDialog
    .locator(".task-document-table tbody tr")
    .first();
  await expect(articleRow).toContainText("可发布");
  const articleTitle = await articleRow.locator("td").first().innerText();
  await taskDialog.getByRole("button", { name: "确认内容，进入发布" }).click();
  await expect(taskDialog.getByText("已确认进入文章发布")).toBeVisible();

  await page.goto(`/publishing?clientId=${clientId}`);
  await expect(
    page.getByRole("heading", { name: "文章发布", level: 1 }),
  ).toBeVisible();
  await expect(page.locator(".article-table tbody tr").first()).toContainText(
    articleTitle.trim(),
  );
});
