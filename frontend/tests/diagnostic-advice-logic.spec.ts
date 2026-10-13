import { describe, expect, it } from "vitest";

import { buildChannelActionPlan } from "../src/diagnosticAdviceLogic";

describe("diagnostic channel action plan", () => {
  it("prioritizes channels that appeared in the current diagnostic sources", () => {
    const plan = buildChannelActionPlan([
      {
        channel_id: "sohu",
        channel_name: "搜狐号 / 搜狐",
        signal_score: 72,
        confidence: "medium",
        source_count: 3,
        question_count: 2,
        competitor_reference_count: 1,
        evidence: [],
      },
    ]);

    expect(plan[0]).toEqual(
      expect.objectContaining({
        channelId: "sohu",
        title: "优先注册或连接搜狐号",
        basis: "observed",
      }),
    );
    expect(plan[0]?.description).toContain("本次诊断");
  });

  it("does not invent baseline channel advice when no source signal exists", () => {
    const plan = buildChannelActionPlan([]);

    expect(plan).toEqual([]);
  });
});
