import { apiClient } from "./client";
import type {
  CircuitBreakerResponse,
  EnhancedStatsResponse,
  HealthReadyResponse,
  LLMUsageResponse,
  StatsResponse,
} from "./types";

export function getStats(): Promise<StatsResponse> {
  return apiClient.get<StatsResponse>("/stats");
}

export function getEnhancedStats(): Promise<EnhancedStatsResponse> {
  return apiClient.get<EnhancedStatsResponse>("/stats/enhanced");
}

export function getLLMUsage(date?: string): Promise<LLMUsageResponse> {
  return apiClient.get<LLMUsageResponse>("/admin/llm-usage", { date });
}

export function getCircuitBreaker(): Promise<CircuitBreakerResponse> {
  return apiClient.get<CircuitBreakerResponse>("/admin/circuit-breaker");
}

export function resetCircuitBreaker(): Promise<CircuitBreakerResponse> {
  return apiClient.post<CircuitBreakerResponse>(
    "/admin/circuit-breaker/reset",
  );
}

export function getHealthReady(): Promise<HealthReadyResponse> {
  return apiClient.get<HealthReadyResponse>("/health/ready");
}
