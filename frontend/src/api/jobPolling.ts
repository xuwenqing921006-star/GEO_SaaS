import type { JobData } from "./dto";

interface JobPollingOptions {
  intervalMs?: number | JobPollingInterval;
  timeoutMs?: number;
  timeoutMessage?: string;
  cancellationMessage?: string;
  now?: () => number;
  sleep?: (milliseconds: number) => Promise<void>;
  isCancelled?: () => boolean;
  onUpdate?: (job: JobData) => void;
}

export interface JobPollingContext {
  attempt: number;
  elapsedMs: number;
  job: JobData;
}

export type JobPollingInterval = (context: JobPollingContext) => number;

interface PollingStage {
  untilMs?: number;
  intervalMs: number;
}

export class JobPollingTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "JobPollingTimeoutError";
  }
}

const terminalStatuses = new Set<JobData["status"]>([
  "succeeded",
  "failed",
  "cancelled",
]);

const defaultSleep = (milliseconds: number): Promise<void> =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export const createStagedPollingInterval = (
  stages: readonly PollingStage[],
): JobPollingInterval => {
  if (!stages.length) throw new Error("轮询阶段不能为空");
  return ({ elapsedMs }) => {
    const stage = stages.find(
      (candidate) =>
        candidate.untilMs === undefined || elapsedMs < candidate.untilMs,
    );
    return Math.max(500, stage?.intervalMs ?? stages.at(-1)!.intervalMs);
  };
};

export const STANDARD_JOB_POLLING_INTERVAL = createStagedPollingInterval([
  { untilMs: 30_000, intervalMs: 3_000 },
  { untilMs: 2 * 60_000, intervalMs: 5_000 },
  { intervalMs: 10_000 },
]);

export const PUBLISHING_JOB_POLLING_INTERVAL = createStagedPollingInterval([
  { untilMs: 30_000, intervalMs: 5_000 },
  { untilMs: 2 * 60_000, intervalMs: 10_000 },
  { intervalMs: 15_000 },
]);

export const formatJobProgress = (job: JobData): string =>
  job.status === "running" && job.progress > 0 && job.progress < 100
    ? `${job.current_step} · ${job.progress}%`
    : job.current_step;

export const pollJobUntilTerminal = async (
  getJob: () => Promise<JobData>,
  options: JobPollingOptions = {},
): Promise<JobData> => {
  const interval = options.intervalMs ?? STANDARD_JOB_POLLING_INTERVAL;
  const timeoutMs = options.timeoutMs ?? 10 * 60_000;
  const now = options.now ?? Date.now;
  const sleep = options.sleep ?? defaultSleep;
  const startedAt = now();
  let attempt = 0;

  while (!(options.isCancelled?.() ?? false)) {
    const job = await getJob();
    attempt += 1;
    if (options.isCancelled?.())
      throw new Error(options.cancellationMessage ?? "任务跟踪已取消");
    options.onUpdate?.(job);
    if (terminalStatuses.has(job.status)) return job;
    const elapsed = now() - startedAt;
    if (elapsed >= timeoutMs)
      throw new JobPollingTimeoutError(
        options.timeoutMessage ?? "任务处理超时，系统已停止等待，请重新发起",
      );
    const intervalMs =
      typeof interval === "number"
        ? interval
        : interval({ attempt, elapsedMs: elapsed, job });
    await sleep(Math.min(Math.max(500, intervalMs), timeoutMs - elapsed));
  }
  throw new Error(options.cancellationMessage ?? "任务跟踪已取消");
};
