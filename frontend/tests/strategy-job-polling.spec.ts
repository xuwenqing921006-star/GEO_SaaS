import { describe, expect, it } from "vitest";
import type { JobData } from "../src/api/dto";
import {
  createStagedPollingInterval,
  formatJobProgress,
  JobPollingTimeoutError,
  pollJobUntilTerminal,
} from "../src/api/jobPolling";

const runningJob = (status: JobData["status"]): JobData => ({
  id: "job-1",
  client_id: "client-1",
  type: "strategy_generate",
  status,
  progress: status === "succeeded" ? 100 : 0,
  current_step: status === "succeeded" ? "已完成" : "生成问题与内容策略",
  attempt: 1,
  max_attempts: 3,
  error_message: null,
  retryable: false,
});

describe("strategy job polling", () => {
  it("does not present an unknown zero as measured progress", () => {
    expect(formatJobProgress(runningJob("running"))).toBe("生成问题与内容策略");
    expect(formatJobProgress({ ...runningJob("running"), progress: 35 })).toBe(
      "生成问题与内容策略 · 35%",
    );
  });

  it("continues beyond 35 seconds and resolves when the model finishes", async () => {
    let elapsed = 0;
    let calls = 0;
    const result = await pollJobUntilTerminal(
      async () => {
        calls += 1;
        return runningJob(calls >= 21 ? "succeeded" : "running");
      },
      {
        intervalMs: 2_000,
        timeoutMs: 10 * 60_000,
        now: () => elapsed,
        sleep: async (milliseconds) => {
          elapsed += milliseconds;
        },
      },
    );

    expect(result.status).toBe("succeeded");
    expect(elapsed).toBe(40_000);
    expect(calls).toBe(21);
  });

  it("stops before sleeping when the page changes during a request", async () => {
    let cancelled = false;
    let sleepCalled = false;

    await expect(
      pollJobUntilTerminal(
        async () => {
          cancelled = true;
          return runningJob("running");
        },
        {
          isCancelled: () => cancelled,
          sleep: async () => {
            sleepCalled = true;
          },
        },
      ),
    ).rejects.toThrow("任务跟踪已取消");

    expect(sleepCalled).toBe(false);
  });

  it("backs off from three seconds to ten seconds for long-running tasks", () => {
    const interval = createStagedPollingInterval([
      { untilMs: 30_000, intervalMs: 3_000 },
      { untilMs: 2 * 60_000, intervalMs: 5_000 },
      { intervalMs: 10_000 },
    ]);
    const job = runningJob("running");

    expect(interval({ attempt: 1, elapsedMs: 0, job })).toBe(3_000);
    expect(interval({ attempt: 8, elapsedMs: 45_000, job })).toBe(5_000);
    expect(interval({ attempt: 20, elapsedMs: 3 * 60_000, job })).toBe(10_000);
  });

  it("returns a clear timeout result after the configured maximum wait", async () => {
    let elapsed = 0;

    await expect(
      pollJobUntilTerminal(async () => runningJob("running"), {
        intervalMs: 3_000,
        timeoutMs: 5_000,
        timeoutMessage: "GEO 诊断等待超过 5 分钟，任务已停止跟踪",
        now: () => elapsed,
        sleep: async (milliseconds) => {
          elapsed += milliseconds;
        },
      }),
    ).rejects.toEqual(
      expect.objectContaining<JobPollingTimeoutError>({
        name: "JobPollingTimeoutError",
        message: "GEO 诊断等待超过 5 分钟，任务已停止跟踪",
      }),
    );

    expect(elapsed).toBe(5_000);
  });
});
