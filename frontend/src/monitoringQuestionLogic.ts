import type {
  MonitoringQuestionData,
  MonitoringQuestionFamily,
  StrategyItemData,
} from "./api/dto";

export const BASELINE_QUESTION_LIMIT = 5;

const keywordFamily: Record<string, MonitoringQuestionFamily> = {
  brand: "brand_verification",
  trust: "brand_verification",
  recommendation: "recommendation",
  decision: "recommendation",
  scenario: "scenario",
  comparison: "comparison",
  transaction: "comparison",
  core: "category_discovery",
  service: "category_discovery",
  geo_longtail: "category_discovery",
  local_service: "category_discovery",
  service_detail: "category_discovery",
};

const familyOrder: MonitoringQuestionFamily[] = [
  "category_discovery",
  "recommendation",
  "brand_verification",
  "scenario",
  "comparison",
];

const toQuestion = (item: StrategyItemData): MonitoringQuestionData | null => {
  const family = keywordFamily[item.keyword_type ?? ""];
  if (!family) return null;
  return {
    id: item.id,
    text: item.text.trim(),
    family,
    is_brand_query: family === "brand_verification",
    target_level:
      item.target_level === "L1" ||
      item.target_level === "L2" ||
      item.target_level === "L3"
        ? item.target_level
        : "L2",
    priority: item.priority,
  };
};

export const selectedKeywordMonitoringQuestions = (
  items: StrategyItemData[],
  limit = BASELINE_QUESTION_LIMIT,
): MonitoringQuestionData[] => {
  const candidates = items
    .filter(
      (item) =>
        item.kind === "keyword" &&
        item.active &&
        item.selected &&
        item.text.trim(),
    )
    .map((item) => ({ item, question: toQuestion(item) }))
    .filter(
      (
        candidate,
      ): candidate is {
        item: StrategyItemData;
        question: MonitoringQuestionData;
      } => candidate.question !== null,
    )
    .sort(
      (left, right) =>
        left.item.priority - right.item.priority ||
        left.item.text.localeCompare(right.item.text, "zh-CN"),
    );

  const selected: MonitoringQuestionData[] = [];
  const selectedIds = new Set<string>();
  for (const family of familyOrder) {
    const candidate = candidates.find(
      ({ item, question }) =>
        question.family === family && !selectedIds.has(item.id),
    );
    if (!candidate) continue;
    selected.push(candidate.question);
    selectedIds.add(candidate.item.id);
    if (selected.length >= limit) return selected;
  }
  for (const candidate of candidates) {
    if (selectedIds.has(candidate.item.id)) continue;
    selected.push(candidate.question);
    selectedIds.add(candidate.item.id);
    if (selected.length >= limit) break;
  }
  return selected;
};
