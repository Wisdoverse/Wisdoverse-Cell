export type CostUsagePeriod = "7d" | "30d" | "90d";

export const COST_USAGE_PERIODS: CostUsagePeriod[] = ["7d", "30d", "90d"];

export function costUsagePeriodDays(period: CostUsagePeriod): number {
  switch (period) {
    case "7d":
      return 7;
    case "30d":
      return 30;
    case "90d":
      return 90;
  }
}
