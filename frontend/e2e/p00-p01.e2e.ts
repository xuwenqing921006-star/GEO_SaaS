import { expect, test, type Page } from "@playwright/test";

const requestId = "00000000-0000-4000-8000-000000000001";

const success = (data: unknown, code: 200 | 201 | 202 = 200) => ({
  code,
  message: code === 201 ? "created" : code === 202 ? "accepted" : "success",
  data,
  request_id: requestId,
});

const error = (code: number, message: string) => ({
  code,
  message,
  data: {
    field_errors: [],
    retryable: false,
    provider: null,
    job_id: null,
  },
  request_id: requestId,
});

const session = {
  user: {
    id: "00000000-0000-4000-8000-000000000010",
    username: "owner",
    display_name: "平台负责人",
  },
  csrf_token: "mock-csrf-token",
  expires_at: "2026-07-28T00:00:00Z",
};

const clientSummary = {
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

const client = {
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
const secondClient = {
  ...clientSummary,
  id: "00000000-0000-4000-8000-000000000102",
  standard_name: "安心家政",
  short_name: "安心",
  industry_code: "housekeeping",
  industry_name: "家政服务",
};

const rejectUnexpectedApiRequests = async (page: Page): Promise<void> => {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify(
        error(
          50000,
          `Unexpected API request: ${route.request().method()} ${new URL(route.request().url()).pathname}`,
        ),
      ),
    }),
  );
};

const routeUnauthenticatedSession = async (page: Page): Promise<void> => {
  await page.route("**/api/v1/auth/session", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify(error(40101, "登录已失效，请重新登录")),
    }),
  );
};

test("owner can log in, search, and create a client from the desktop workspace", async ({
  page,
}) => {
  await rejectUnexpectedApiRequests(page);
  await routeUnauthenticatedSession(page);
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(success(session)),
    }),
  );
  await page.route("**/api/v1/clients?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          items: [clientSummary],
          page: 1,
          page_size: 20,
          total: 1,
          has_next: false,
        }),
      ),
    }),
  );
  await page.route("**/api/v1/clients", (route) => {
    const isCreateRequest = route.request().method() === "POST";
    return route.fulfill({
      status: isCreateRequest ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(
        isCreateRequest
          ? success(client, 201)
          : success({
              items: [clientSummary],
              page: 1,
              page_size: 20,
              total: 1,
              has_next: false,
            }),
      ),
    });
  });
  await page.route(`**/api/v1/clients/${client.id}/dashboard`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
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
          next_actions: [],
          recent_jobs: [],
        }),
      ),
    }),
  );

  await page.goto("/clients");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("correct-password");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "客户工作台" })).toBeVisible();
  await expect(page.getByText("Mock", { exact: true })).toHaveCount(0);

  await page.keyboard.press("/");
  await page.getByRole("searchbox", { name: "搜索客户" }).fill("莱恩");
  await expect(
    page.getByRole("button", { name: "选择莱恩美术" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "新建客户" }).click();
  const createDialog = page.getByRole("dialog", { name: "新建客户" });
  await createDialog.getByLabel("企业名称").fill("莱恩美术");
  await createDialog.getByLabel("行业代码").fill("art_education");
  await createDialog.getByLabel("省份").fill("北京市");
  await createDialog.getByLabel("城市").fill("北京市");
  await createDialog.getByLabel("区县").fill("朝阳区");
  await createDialog.getByLabel("详细地址").fill("望京路 1 号");
  await createDialog.getByLabel("合作开始日期").fill("2026-01-01");
  await createDialog.getByRole("button", { name: "创建客户" }).click();
  await expect(page.getByRole("status")).toContainText("客户创建成功");
});

test("small viewports receive the desktop-only notice", async ({ page }) => {
  await page.setViewportSize({ width: 479, height: 900 });
  await rejectUnexpectedApiRequests(page);
  await routeUnauthenticatedSession(page);
  await page.goto("/");

  await expect(page.getByText("请使用桌面浏览器访问")).toBeVisible();
});

test("discarding customer edits restores scrolling before a recoverable failed logout", async ({
  page,
}) => {
  let logoutAttempts = 0;
  await rejectUnexpectedApiRequests(page);
  await page.route("**/api/v1/auth/session", (route) => {
    if (route.request().method() === "DELETE") {
      logoutAttempts += 1;
      return route.fulfill({
        status: logoutAttempts === 1 ? 500 : 200,
        contentType: "application/json",
        body: JSON.stringify(
          logoutAttempts === 1
            ? error(50001, "服务暂时不可用")
            : success({ logged_out: true }),
        ),
      });
    }
    return route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify(error(40101, "登录已失效，请重新登录")),
    });
  });
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(success(session)),
    }),
  );
  await page.route("**/api/v1/clients?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          items: [clientSummary, secondClient],
          page: 1,
          page_size: 20,
          total: 2,
          has_next: false,
        }),
      ),
    }),
  );
  await page.route("**/api/v1/clients/*/dashboard", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          client: clientSummary,
          counts: {
            materials: 0,
            confirmed_facts: 0,
            unresolved_conflicts: 0,
            planned_contents: 0,
            draft_contents: 0,
            monitoring_samples_30d: 0,
          },
          level_progress: {
            current: "L1",
            next: "L2",
            missing_conditions: [],
          },
          next_actions: [],
          recent_jobs: [],
        }),
      ),
    }),
  );

  await page.goto("/clients");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("correct-password");
  await page.getByRole("button", { name: "登录" }).click();
  await page.getByRole("button", { name: "编辑莱恩美术" }).click();
  await page.getByRole("textbox", { name: "企业名称" }).fill("莱恩少儿美术");
  await page.getByRole("button", { name: "取消" }).click();

  const editCloseDialog = page.getByRole("dialog", {
    name: "未保存的客户资料",
  });
  await expect(editCloseDialog).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(2);
  await editCloseDialog.getByRole("button", { name: "放弃修改" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => document.body.style.overflow))
    .toBe("");

  await page.getByRole("button", { name: "账户菜单" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();

  const accountDialog = page.getByRole("dialog", { name: "账户菜单" });
  await expect(accountDialog.getByRole("alert")).toContainText(
    "退出失败，请重试",
  );
  await accountDialog.getByRole("button", { name: "重试" }).click();

  await expect(page).toHaveURL(/\/login/);
  expect(logoutAttempts).toBe(2);
});

test("failed logout keeps a clickable retry inside the account dialog", async ({
  page,
}) => {
  let logoutAttempts = 0;
  await rejectUnexpectedApiRequests(page);
  await page.route("**/api/v1/auth/session", (route) => {
    if (route.request().method() === "DELETE") {
      logoutAttempts += 1;
      return route.fulfill({
        status: logoutAttempts === 1 ? 500 : 200,
        contentType: "application/json",
        body: JSON.stringify(
          logoutAttempts === 1
            ? error(50001, "服务暂时不可用")
            : success({ logged_out: true }),
        ),
      });
    }
    return route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify(error(40101, "登录已失效，请重新登录")),
    });
  });
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(success(session)),
    }),
  );
  await page.route("**/api/v1/clients?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          items: [clientSummary],
          page: 1,
          page_size: 20,
          total: 1,
          has_next: false,
        }),
      ),
    }),
  );
  await page.route("**/api/v1/clients/*/dashboard", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          client: clientSummary,
          counts: {
            materials: 0,
            confirmed_facts: 0,
            unresolved_conflicts: 0,
            planned_contents: 0,
            draft_contents: 0,
            monitoring_samples_30d: 0,
          },
          level_progress: {
            current: "L1",
            next: "L2",
            missing_conditions: [],
          },
          next_actions: [],
          recent_jobs: [],
        }),
      ),
    }),
  );

  await page.goto("/clients");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("correct-password");
  await page.getByRole("button", { name: "登录" }).click();
  await page.getByRole("button", { name: "账户菜单" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();

  const accountDialog = page.getByRole("dialog", { name: "账户菜单" });
  await expect(accountDialog.getByRole("alert")).toContainText(
    "退出失败，请重试",
  );
  await accountDialog.getByRole("button", { name: "重试" }).click();

  await expect(page).toHaveURL(/\/login/);
  expect(logoutAttempts).toBe(2);
});

test("1024 and 1280 desktop workspaces do not overflow horizontally", async ({
  page,
}) => {
  await rejectUnexpectedApiRequests(page);
  await routeUnauthenticatedSession(page);
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(success(session)),
    }),
  );
  await page.route("**/api/v1/clients?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          items: [clientSummary, secondClient],
          page: 1,
          page_size: 20,
          total: 2,
          has_next: false,
        }),
      ),
    }),
  );
  await page.route("**/api/v1/clients/*/dashboard", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        success({
          client: clientSummary,
          counts: {
            materials: 0,
            confirmed_facts: 0,
            unresolved_conflicts: 0,
            planned_contents: 0,
            draft_contents: 0,
            monitoring_samples_30d: 0,
          },
          level_progress: {
            current: "L1",
            next: "L2",
            missing_conditions: [],
          },
          next_actions: [],
          recent_jobs: [],
        }),
      ),
    }),
  );
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto("/clients");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("correct-password");
  await page.getByRole("button", { name: "登录" }).click();
  for (const width of [1024, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(
      page.getByRole("heading", { name: "客户工作台" }),
    ).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
  }
});
