import { expect, test } from "@playwright/test";

test("real P02 imports source material and manages the resulting knowledge entry", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("CorrectPassword2026!");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/clients/);

  const session = await page.request.get("/api/v1/auth/session");
  expect(session.ok()).toBeTruthy();
  const csrfToken = (await session.json()).data.csrf_token as string;
  const created = await page.request.post("/api/v1/clients", {
    headers: { "X-CSRF-Token": csrfToken },
    data: {
      standard_name: "T007 真实知识库客户",
      short_name: "T007 客户",
      industry_code: "repair",
      province: "山东省",
      city: "青岛市",
      district: "即墨区",
      address: "即墨区测试地址",
      contact_phone: null,
      contact_wechat: null,
      business_hours: "09:00-18:00",
      service_radius: "即墨区",
      cooperation_started_on: "2026-07-27",
      notes: "真实 P02 浏览器验收客户",
    },
  });
  expect(created.status()).toBe(201);
  const clientId = (await created.json()).data.id as string;

  await page.goto(`/knowledge?clientId=${clientId}`);
  await expect(
    page.getByRole("heading", { name: "企业知识库", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "下载客户资料模板" }).first(),
  ).toBeVisible();

  await page.getByLabel("选择资料文件").setInputFiles({
    name: "服务资料.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("服务项目: 家电维修\n服务范围: 即墨区"),
  });
  await page.getByRole("button", { name: "上传并导入知识库" }).click();
  await expect(
    page.getByText("资料已上传，系统正在整理知识条目。"),
  ).toBeVisible();
  await expect(page.getByText("服务资料.txt")).toBeVisible();
  await expect(page.getByText("已导入", { exact: true })).toBeVisible({
    timeout: 30_000,
  });

  const records = page.locator(".knowledge-records-card");
  await expect(records.getByText("服务项目")).toBeVisible();
  await records.getByRole("button", { name: "编辑服务项目" }).click();
  const editor = page.getByRole("dialog", { name: "编辑知识条目" });
  await editor.getByLabel("详细内容").fill("提供家电与水电维修服务");
  await editor.getByRole("button", { name: "保存到知识库" }).click();
  await expect(records.getByText("提供家电与水电维修服务")).toBeVisible();
});
