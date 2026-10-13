import { expect, test, type APIRequestContext } from "@playwright/test";

const createConfirmedFact = async (
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
  expect(withEvidence.status()).toBe(201);
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

test("real P03 and P04 generate and confirm a keyword task from local facts", async ({
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
      standard_name: "莱恩美术 E2E",
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
      notes: "T008 真实策略浏览器验收客户",
    },
  });
  expect(created.status()).toBe(201);
  const clientId = (await created.json()).data.id as string;

  await createConfirmedFact(page.request, csrfToken, clientId, {
    category: "service",
    key: "service.primary",
    label: "核心服务",
    value: "少儿美术培训",
  });
  await createConfirmedFact(page.request, csrfToken, clientId, {
    category: "audience",
    key: "audience.primary",
    label: "适用客群",
    value: "即墨区 4—12 岁儿童及家长",
  });
  await createConfirmedFact(page.request, csrfToken, clientId, {
    category: "location",
    key: "location.service_area",
    label: "服务范围",
    value: "即墨区",
  });

  await page.goto(`/diagnostics?clientId=${clientId}`);
  await expect(
    page.getByRole("heading", { name: "GEO 诊断", level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "开始诊断" }).click();
  await expect(page.getByText("AI 平台收录与推荐表现")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".platform-result-table tbody tr")).toHaveCount(4);
  await expect(page.locator(".diagnosis-probe-questions p")).toHaveCount(3);

  await page.getByRole("button", { name: "生成关键词" }).click();
  await expect(page).toHaveURL(new RegExp(`/strategy\\?clientId=${clientId}`));
  await page.getByRole("button", { name: "确认并生成关键词" }).click();

  const candidates = page.getByRole("dialog", {
    name: "查看本次生成的关键词",
  });
  await expect(
    candidates.locator(".candidate-list article").first(),
  ).toBeVisible({
    timeout: 30_000,
  });
  await candidates.getByLabel("全选本页").check();
  await candidates.getByRole("button", { name: /确认保存/ }).click();

  await expect(candidates).toBeHidden();
  await expect(
    page.locator(".confirmed-keyword-grid article").first(),
  ).toBeVisible();
  await expect(
    page.locator(".keyword-task-table tbody tr").first(),
  ).toContainText("已保存");
});
