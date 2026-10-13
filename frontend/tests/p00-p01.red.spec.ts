import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/vue";
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

import {
  apiRequests,
  client,
  clientSummary,
  clientsPage,
  dashboard,
  errorResponse,
  server,
  session,
  successResponse,
} from "./fixtures/api";
import { renderApplication } from "./fixtures/runtime";

const loginAsOwner = async (): Promise<void> => {
  await screen.findByRole("heading", { name: "负责人登录" });
  await fireEvent.update(screen.getByLabelText("用户名"), "owner");
  await fireEvent.update(screen.getByLabelText("密码"), "correct-password");
  await fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await screen.findByRole("searchbox", { name: "搜索客户" });
};

describe("P00 / P01 RED acceptance tests", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

  beforeEach(() => {
    apiRequests.length = 0;
    window.history.replaceState({}, "", "/clients");
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(successResponse(session)),
      ),
      http.get("/api/v1/clients", () => HttpResponse.json(clientsPage())),
      http.get("/api/v1/clients/:clientId", () =>
        HttpResponse.json(successResponse(client)),
      ),
      http.get("/api/v1/clients/:clientId/dashboard", () =>
        HttpResponse.json(dashboard()),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    server.resetHandlers();
  });

  afterAll(() => server.close());

  it("redirects an unauthenticated visitor to the single-owner login page", async () => {
    await renderApplication();

    expect(
      await screen.findByRole("heading", { name: "负责人登录" }),
    ).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "用户名" })).toBeTruthy();
    expect(screen.getByLabelText("密码").getAttribute("type")).toBe("password");
    expect(
      screen.queryByRole("button", { name: /第三方登录|注册/ }),
    ).toBeNull();
  });

  it("shows the contract login error and keeps the form available when credentials are rejected", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(errorResponse(40102, "用户名或密码错误"), {
          status: 401,
        }),
      ),
    );
    await renderApplication();

    await screen.findByRole("heading", { name: "负责人登录" });
    await fireEvent.update(screen.getByLabelText("用户名"), "owner");
    await fireEvent.update(screen.getByLabelText("密码"), "not-the-password");
    await fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "用户名或密码错误",
    );
    expect(
      screen.getByRole("button", { name: "登录" }).hasAttribute("disabled"),
    ).toBe(false);
  });

  it("establishes the session after a successful login and shows the client workspace", async () => {
    await renderApplication();

    await loginAsOwner();

    expect(
      await screen.findByRole("heading", { name: "客户工作台" }),
    ).toBeTruthy();
    expect(
      await screen.findByRole("button", { name: "选择莱恩美术" }),
    ).toBeTruthy();
  });

  it("sends the customer search as the q query parameter", async () => {
    await renderApplication();
    await loginAsOwner();

    await fireEvent.update(
      screen.getByRole("searchbox", { name: "搜索客户" }),
      "莱恩",
    );

    await waitFor(() => {
      expect(
        apiRequests.some(
          (url) =>
            url.pathname === "/api/v1/clients" &&
            url.searchParams.get("q") === "莱恩",
        ),
      ).toBe(true);
    });
  });

  it("presents normal, loading, empty, and error client-list states without hiding the page heading", async () => {
    server.use(
      http.get("/api/v1/clients", async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json(clientsPage([clientSummary]));
      }),
    );
    await renderApplication();
    await loginAsOwner();

    expect(
      await screen.findByRole("status", { name: "正在加载客户" }),
    ).toBeTruthy();
    expect(
      await screen.findByRole("button", { name: "选择莱恩美术" }),
    ).toBeTruthy();

    cleanup();
    server.use(
      http.get("/api/v1/clients", () => HttpResponse.json(clientsPage([]))),
    );
    await renderApplication();
    await loginAsOwner();
    expect(await screen.findByText("暂无客户")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "客户工作台" })).toBeTruthy();

    cleanup();
    server.use(
      http.get("/api/v1/clients", () =>
        HttpResponse.json(errorResponse(50001, "客户列表暂时不可用"), {
          status: 500,
        }),
      ),
    );
    await renderApplication();
    await loginAsOwner();
    expect((await screen.findByRole("alert")).textContent).toContain(
      "客户列表暂时不可用",
    );
    expect(screen.getByRole("heading", { name: "客户工作台" })).toBeTruthy();
  });

  it("keeps the customer task usable without depending on a separate dashboard request", async () => {
    server.use(
      http.get(`/api/v1/clients/${client.id}/dashboard`, () =>
        HttpResponse.json(errorResponse(50001, "工作台数据暂时不可用"), {
          status: 500,
        }),
      ),
    );
    await renderApplication();
    await loginAsOwner();

    await fireEvent.click(
      await screen.findByRole("button", { name: "选择莱恩美术" }),
    );

    expect(screen.getByRole("button", { name: "选择莱恩美术" })).toBeTruthy();
    const row = screen.getByRole("row", { name: /莱恩美术/ });
    expect(within(row).getByText("补充服务范围")).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "莱恩美术下一步" }),
    ).toBeNull();
  });

  it("merges GEO progress and the next task into the client list with view, edit, and recoverable delete actions", async () => {
    server.use(
      http.get(`/api/v1/clients/${client.id}`, () =>
        HttpResponse.json(successResponse(client)),
      ),
    );
    await renderApplication();
    await loginAsOwner();

    const row = await screen.findByRole("row", { name: /莱恩美术/ });
    expect(within(row).getByText("补充服务范围")).toBeTruthy();
    expect(within(row).getByText("可开始 GEO 工作")).toBeTruthy();
    expect(within(row).getByText("2 项需关注")).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "莱恩美术下一步" }),
    ).toBeNull();

    await fireEvent.click(
      within(row).getByRole("button", { name: "查看莱恩美术" }),
    );
    const viewDialog = await screen.findByRole("dialog", {
      name: "查看客户 · 莱恩美术",
    });
    expect(within(viewDialog).getByText("当前任务")).toBeTruthy();
    await fireEvent.click(
      within(viewDialog).getByRole("button", { name: "关闭" }),
    );

    await fireEvent.click(
      within(row).getByRole("button", { name: "编辑莱恩美术" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "编辑客户 · 莱恩美术" }),
    ).toBeTruthy();
    await fireEvent.click(await screen.findByRole("button", { name: "取消" }));

    await fireEvent.click(
      within(row).getByRole("button", { name: "删除莱恩美术" }),
    );
    const deleteDialog = await screen.findByRole("dialog", {
      name: "删除客户 · 莱恩美术",
    });
    expect(within(deleteDialog).getByText(/可恢复/)).toBeTruthy();
  });

  it("restores page scrolling after discarding edits from a nested confirmation dialog", async () => {
    await renderApplication();
    await loginAsOwner();

    await fireEvent.click(
      await screen.findByRole("button", { name: "编辑莱恩美术" }),
    );
    await fireEvent.update(
      await screen.findByLabelText("详细地址"),
      "即墨区新地址 18 号",
    );
    await fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await screen.findByRole("dialog", { name: "未保存的客户资料" });
    expect(document.body.style.overflow).toBe("hidden");

    await fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "未保存的客户资料" }),
      ).toBeNull();
      expect(
        screen.queryByRole("dialog", { name: "编辑客户 · 莱恩美术" }),
      ).toBeNull();
      expect(document.body.style.overflow).toBe("");
    });
  });

  it("prevents discarding edits while the save request is still running", async () => {
    let releasePatch: (() => void) | undefined;
    const patchGate = new Promise<void>((resolve) => {
      releasePatch = resolve;
    });
    server.use(
      http.patch(`/api/v1/clients/${client.id}`, async () => {
        await patchGate;
        return HttpResponse.json(
          successResponse({
            ...clientSummary,
            standard_name: "莱恩少儿美术",
            version: 2,
          }),
        );
      }),
    );
    await renderApplication();
    await loginAsOwner();

    await fireEvent.click(
      await screen.findByRole("button", { name: "编辑莱恩美术" }),
    );
    await fireEvent.update(
      await screen.findByLabelText("企业名称"),
      "莱恩少儿美术",
    );
    await fireEvent.click(screen.getByRole("button", { name: "取消" }));
    const confirmation = await screen.findByRole("dialog", {
      name: "未保存的客户资料",
    });
    await fireEvent.click(
      within(confirmation).getByRole("button", {
        name: "保存修改并关闭",
      }),
    );

    for (const name of ["关闭", "继续编辑", "放弃修改"]) {
      expect(
        (
          within(confirmation).getByRole("button", {
            name,
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true);
    }
    expect(document.body.style.overflow).toBe("hidden");

    releasePatch?.();
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "未保存的客户资料" }),
      ).toBeNull();
      expect(document.body.style.overflow).toBe("");
    });
  });

  it("validates required customer fields and confirms a created customer", async () => {
    const createdClient = {
      ...clientSummary,
      id: "00000000-0000-4000-8000-000000000109",
      standard_name: "新建测试客户",
    };
    let listedClients = [clientSummary];
    server.use(
      http.get("/api/v1/clients", () =>
        HttpResponse.json(clientsPage(listedClients)),
      ),
      http.post("/api/v1/clients", () => {
        listedClients = [createdClient, ...listedClients];
        return HttpResponse.json(successResponse(createdClient, 201), {
          status: 201,
        });
      }),
    );
    await renderApplication();
    await loginAsOwner();

    await fireEvent.click(
      await screen.findByRole("button", { name: "新建客户" }),
    );
    await fireEvent.click(screen.getByRole("button", { name: "创建客户" }));
    expect(await screen.findByText("请填写企业名称")).toBeTruthy();

    await fireEvent.update(
      screen.getByLabelText("企业名称"),
      createdClient.standard_name,
    );
    await fireEvent.update(
      screen.getByLabelText("行业代码"),
      client.industry_code,
    );
    await fireEvent.update(screen.getByLabelText("省份"), client.province);
    await fireEvent.update(screen.getByLabelText("城市"), client.city);
    await fireEvent.update(screen.getByLabelText("区县"), client.district);
    await fireEvent.update(screen.getByLabelText("详细地址"), client.address);
    await fireEvent.update(
      screen.getByLabelText("合作开始日期"),
      client.cooperation_started_on,
    );
    await fireEvent.click(screen.getByRole("button", { name: "创建客户" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("客户创建成功"),
    );
    expect(
      await screen.findByRole("button", { name: "选择新建测试客户" }),
    ).toBeTruthy();
  });

  it("offers save, discard, and cancel before switching away from unsaved customer edits", async () => {
    await renderApplication();
    await loginAsOwner();

    await fireEvent.click(
      await screen.findByRole("button", { name: "编辑莱恩美术" }),
    );
    await fireEvent.update(
      await screen.findByLabelText("企业名称"),
      "莱恩少儿美术",
    );
    await fireEvent.click(screen.getByRole("button", { name: "选择安心家政" }));

    const dialog = await screen.findByRole("dialog", { name: "未保存的更改" });
    expect(
      within(dialog).getByRole("button", { name: "保存并切换" }),
    ).toBeTruthy();
    expect(
      within(dialog).getByRole("button", { name: "放弃并切换" }),
    ).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "取消" })).toBeTruthy();
    await fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(
      screen
        .getByRole("button", { name: "选择莱恩美术" })
        .getAttribute("aria-pressed"),
    ).toBe("true");

    await fireEvent.click(screen.getByRole("button", { name: "选择安心家政" }));
    await fireEvent.click(
      await screen.findByRole("button", { name: "放弃并切换" }),
    );
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "选择安心家政" })
          .getAttribute("aria-pressed"),
      ).toBe("true"),
    );
  });

  it("shows the compact-screen notice below 480px and supports slash-search plus Escape dismissal", async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 479,
    });
    window.dispatchEvent(new Event("resize"));
    await renderApplication();

    expect(await screen.findByText("请使用桌面浏览器访问")).toBeTruthy();
    cleanup();

    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1280,
    });
    window.dispatchEvent(new Event("resize"));
    await renderApplication();
    await loginAsOwner();
    await fireEvent.keyDown(window, { key: "/" });
    expect(await screen.findByRole("searchbox", { name: "搜索客户" })).toBe(
      document.activeElement,
    );

    await fireEvent.click(screen.getByRole("button", { name: "新建客户" }));
    expect(
      await screen.findByRole("dialog", { name: "新建客户" }),
    ).toBeTruthy();
    await fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "新建客户" })).toBeNull(),
    );
  });
});
