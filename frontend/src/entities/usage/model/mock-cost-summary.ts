export type CostUsagePeriod = "7d" | "30d" | "90d";

export const COST_USAGE_PERIODS: CostUsagePeriod[] = ["7d", "30d", "90d"];

export const MOCK_COST_SUMMARY = {
  totalCost: 1247.83,
  totalTokens: 15_420_000,
  avgDailyCost: 41.59,
};
