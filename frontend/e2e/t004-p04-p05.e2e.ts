import { expect, test, type Page } from "@playwright/test";

const clientId = "00000000-0000-4000-8000-000000000101";
const clientWithoutKeywordsId = "00000000-0000-4000-8000-000000000102";
const unknownClientId = "00000000-0000-4000-8000-000000000999";

const signIn = async (page: Page): Promise<void> => {
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("GeoSaaS2026!");
  await page.getByRole("button", { name: "登录" }).click();
};

const ensureFirstKeywordSelected = async (page: Page): Promise<void> => {
  const keywordCheckbox = page
    .getByRole("table", { name: "GEO 关键词建议列表" })
    .getByRole("checkbox")
    .nth(1);
  if (!(await keywordCheckbox.isChecked())) await keywordCheckbox.click();
  await expect(keywordCheckbox).toBeChecked();
};

test("operator can edit a keyword and hand it to AI content generation", async ({
  page,
}) => {
  await page.goto(`/strategy?clientId=${clientId}`);
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "关键词", level: 1 }),
  ).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).first().click();
  await expect(page.getByRole("dialog", { name: "编辑关键词" })).toBeVisible();
  await page.getByLabel("主关键词").fill("即墨少儿美术");
  await page
    .getByLabel("长尾关键词 / 用户问题")
    .fill("即墨少儿美术课程选择前要了解什么？");
  await page.getByRole("button", { name: "保存关键词" }).click();
  await expect(
    page.getByText("即墨少儿美术课程选择前要了解什么？"),
  ).toBeVisible();

  await ensureFirstKeywordSelected(page);
  await expect(page.getByText("已选择 1 项", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "批量生成内容" }).click();

  await expect(
    page.getByRole("heading", { name: "内容工作台", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByText("已选择 1 个关键词。", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始 AI 生成" }),
  ).toBeEnabled();
});

test("AI generation controls use selected keywords and show an article list", async ({
  page,
}) => {
  await page.goto(`/strategy?clientId=${clientId}`);
  await signIn(page);
  await ensureFirstKeywordSelected(page);
  await page.getByRole("button", { name: "内容工作台", exact: true }).click();

  await expect(
    page.getByRole("heading", { name: "AI 生成文章", level: 2 }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始 AI 生成" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("heading", { name: "文章列表", level: 2 }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "AI 生成文章列表" }),
  ).toBeVisible();
  await expect(page.getByLabel("按关键词或标题筛选")).toBeVisible();
  await expect(page.getByLabel("发布状态")).toBeVisible();
});

test("content controls stay usable on a narrow desktop window", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto(`/content?clientId=${clientId}`);
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "内容工作台", level: 1 }),
  ).toBeVisible();

  const generator = await page.locator(".content-generator").boundingBox();
  const articleList = await page.locator(".article-list-panel").boundingBox();
  expect(generator).not.toBeNull();
  expect(articleList).not.toBeNull();
  expect(articleList!.y).toBeGreaterThan(generator!.y);

  await page.locator("details.channel-multi-select summary").click();
  const channelOptions = await page
    .locator(".channel-multi-options")
    .boundingBox();
  expect(channelOptions).not.toBeNull();
  expect(channelOptions!.x).toBeGreaterThanOrEqual(0);
  expect(channelOptions!.x + channelOptions!.width).toBeLessThanOrEqual(1024);
});

test("content workbench does not invent keywords for another client", async ({
  page,
}) => {
  await page.goto(`/content?clientId=${clientWithoutKeywordsId}`);
  await signIn(page);
  await expect(page.getByText("还没有选择关键词")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始 AI 生成" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("cell", {
      name: "暂无文章。选择关键词并配置篇数后，点击“开始 AI 生成”。",
    }),
  ).toBeVisible();
});

test("content workbench reports an unknown client without showing article data", async ({
  page,
}) => {
  await page.goto(`/content?clientId=${unknownClientId}`);
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText("客户不存在");
  await expect(
    page.getByRole("button", { name: "开始 AI 生成" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("table", { name: "AI 生成文章列表" }).getByRole("row"),
  ).toHaveCount(2);
});
