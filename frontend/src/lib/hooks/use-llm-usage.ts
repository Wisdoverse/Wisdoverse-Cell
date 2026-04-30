import useSWR from "swr";
import { getLLMUsage, getCircuitBreaker, getHealthReady } from "@/lib/api/admin";

export function useLLMUsage(date?: string) {
  return useSWR(["llm-usage", date], () => getLLMUsage(date), {
    refreshInterval: 10000,
  });
}

export function useCircuitBreaker() {
  return useSWR("circuit-breaker", getCircuitBreaker, {
    refreshInterval: 10000,
  });
}

export function useHealthReady() {
  return useSWR("health-ready", getHealthReady, { refreshInterval: 10000 });
}
