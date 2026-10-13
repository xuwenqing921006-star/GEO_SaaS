import { expect, test, type Page } from "@playwright/test";

const laineClientId = "00000000-0000-4000-8000-000000000101";
const incompleteClientId = "00000000-0000-4000-8000-000000000102";

const signIn = async (page: Page, path: string): Promise<void> => {
  await page.goto(path);
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("GeoSaaS2026!");
  await page.getByRole("button", { name: "登录" }).click();
};

test("operator can manage enterprise knowledge, then open GEO diagnostics", async ({
  page,
}) => {
  await signIn(page, `/knowledge?clientId=${laineClientId}`);

  await expect(
    page.getByRole("heading", { name: "企业知识库", level: 1 }),
  ).toBeVisible();
  await expect(page.locator(".client-context")).toContainText("莱恩美术");
  await expect(page.getByText("机构标准名称")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "下载客户资料模板" }).first(),
  ).toHaveAttribute("download", "");
  await page.getByRole("button", { name: "编辑机构标准名称" }).click();
  await expect(
    page.getByRole("dialog", { name: "编辑知识条目" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "GEO 诊断", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "GEO 诊断", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText("AI 平台收录与推荐表现")).toBeVisible();
  await expect(page.getByText("综合评分", { exact: true })).toBeVisible();
  await expect(page.getByText("服务范围尚未确认")).toBeVisible();
  await expect(page.getByText("五维诊断")).toHaveCount(0);
});

test("operator sees a blocker instead of a made-up score for an incomplete client", async ({
  page,
}) => {
  await signIn(page, `/diagnostics?clientId=${incompleteClientId}`);

  await expect(page.getByText("还没有 GEO 诊断结果")).toBeVisible();
  await expect(page.getByText("暂无足够的自动检测回答")).toHaveCount(0);
  await expect(page.getByText("综合评分", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "开始首次诊断" }),
  ).toBeVisible();
});
