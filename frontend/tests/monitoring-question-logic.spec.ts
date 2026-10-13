import { describe, expect, it } from "vitest";
import type { StrategyItemData } from "../src/api/dto";
import {
  BASELINE_QUESTION_LIMIT,
  selectedKeywordMonitoringQuestions,
} from "../src/monitoringQuestionLogic";

const keyword = (
  id: string,
  keywordType: StrategyItemData["keyword_type"],
  overrides: Partial<StrategyItemData> = {},
): StrategyItemData => ({
  id,
  kind: "keyword",
  text: `${id}用户问题`,
  family: null,
  keyword_type: keywordType,
  provenance: "ai_generated",
  target_level: "L2",
  priority: 1,
  rationale: "监测问题",
  main_keyword: id,
  user_intent: "了解服务",
  recommended_content_type: "faq",
  locked: false,
  selected: true,
  active: true,
  generated_count: 0,
  version: 1,
  ...overrides,
});

describe("selectedKeywordMonitoringQuestions", () => {
  it("优先抽取不同用户意图并限制首轮监测问题数量", () => {
    const result = selectedKeywordMonitoringQuestions([
      keyword("地区主营", "local_service"),
      keyword("推荐决策", "recommendation"),
      keyword("企业品牌", "brand"),
      keyword("场景适配", "scenario"),
      keyword("选择比较", "comparison"),
      keyword("费用流程", "transaction"),
    ]);

    expect(result).toHaveLength(BASELINE_QUESTION_LIMIT);
    expect(result.map((item) => item.family)).toEqual([
      "category_discovery",
      "recommendation",
      "brand_verification",
      "scenario",
      "comparison",
    ]);
    expect(result[2]?.is_brand_query).toBe(true);
  });

  it("只使用已勾选且有效的关键词，并把 L4 转为监测支持的 L2", () => {
    const result = selectedKeywordMonitoringQuestions([
      keyword("未选择", "local_service", { selected: false }),
      keyword("已删除", "brand", { active: false }),
      keyword("隐藏问题", "scenario", { kind: "question" }),
      keyword("有效关键词", "trust", { target_level: "L4" }),
    ]);

    expect(result).toEqual([
      expect.objectContaining({
        id: "有效关键词",
        family: "brand_verification",
        target_level: "L2",
      }),
    ]);
  });
});
