// Enums
export type ApprovalType = "finance" | "legal" | "technical" | "customer";
export type RequirementStatus = "pending" | "confirmed" | "changed" | "rejected";
export type Priority = "high" | "medium" | "low";
export type Category = "功能" | "性能" | "硬件" | "集成" | "UI" | "安全" | "其他";
export type QuestionStatus = "open" | "answered" | "dismissed";
export type CircuitBreakerState = "closed" | "open" | "half-open" | "half_open";
export type HealthStatus = "ok" | "healthy" | "unhealthy" | "degraded";
export type IngestStatus = "success" | "partial" | "failed";
export type MessageType = "text" | "image" | "file" | "system";

// Core Models
export interface Requirement {
  id: string;
  title: string;
  description: string;
  source_quote: string | null;
  status: RequirementStatus;
  priority: Priority;
  category: Category;
  source_meeting_ids: string[];
  confirmed_by: string | null;
  confirmed_at: string | null;
  rejection_reason: string | null;
  open_questions: OpenQuestion[];
  history: HistoryEntry[];
  created_at: string;
  updated_at: string;
}

export interface RequirementListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Requirement[];
}

export interface RequirementUpdateRequest {
  title?: string;
  description?: string;
  priority?: Priority;
  category?: Category;
  comment?: string;
}

export interface OpenQuestion {
  id: string;
  question: string;
  context: string | null;
  status: QuestionStatus;
  answer: string | null;
  answered_by: string | null;
  created_at: string;
  answered_at: string | null;
}

export interface HistoryEntry {
  timestamp: string;
  action: string;
  changes: Record<string, unknown>;
  by: string | null;
}

export interface IngestRequest {
  source: string;
  content: string;
  title?: string | null;
  meeting_date?: string | null;
  participants?: string[];
  context?: string | null;
}

export interface IngestResponse {
  status: IngestStatus;
  meeting_id: string;
  requirements_extracted: number;
  questions_generated: number;
}

export interface StatsResponse {
  requirements_by_status: Record<string, number>;
}

export interface EnhancedStatsResponse {
  requirements_by_status: Record<string, number>;
  weekly_trend: { date: string; count: number }[];
}

export interface LLMUsageResponse {
  date?: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_calls: number;
  success_calls?: number;
  failed_calls?: number;
  avg_latency_ms: number;
  by_agent?: Record<
    string,
    {
      calls: number;
      cost_usd: number;
      input_tokens: number;
      output_tokens: number;
    }
  >;
  by_task_type?: Record<
    string,
    {
      calls: number;
      cost_usd: number;
    }
  >;
}

export interface CircuitBreakerResponse {
  state: CircuitBreakerState;
}

export interface HealthReadyResponse {
  status: HealthStatus;
  checks: Record<string, { status: HealthStatus; latency_ms?: number }>;
}

export interface ConflictCheckRequest {
  title: string;
  description: string;
}

export interface ConflictCheckResponse {
  relation: "new" | "duplicate" | "update" | "conflict";
  confidence: number;
  explanation: string;
  suggested_action: string;
  related_requirement_id: string | null;
  merge_suggestion: string | null;
}

export interface BatchOperationResponse {
  total: number;
  succeeded: number;
  failed: number;
  results: { requirement_id: string; success: boolean; error?: string }[];
}

export interface SemanticSearchResponse {
  items: Requirement[];
  total: number;
}

export interface SimilarRequirement {
  requirement: Requirement;
  similarity: number;
}

export interface MessageSearchResult {
  id: string;
  chat_id: string;
  sender_id: string;
  sender_name: string;
  message_type: MessageType;
  content: string;
  session_id: string | null;
  extracted: boolean;
  sent_at: string;
}

export interface MessageSession {
  session_id: string;
  messages: MessageSearchResult[];
}

export interface PRDExportResponse {
  content: string;
  format: string;
  generated_at: string;
}

export interface ApiError {
  detail: string;
  status: number;
}

// Query parameter types
export interface RequirementFilters {
  status?: RequirementStatus;
  category?: Category;
  priority?: Priority;
  page?: number;
  page_size?: number;
}

export interface MessageSearchParams {
  chat_id?: string;
  keyword?: string;
  sender_id?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface ApprovalRequest {
  id: string;
  source_agent_id: string;
  approval_type: ApprovalType;
  title: string;
  summary: string;
  context_link?: string;
  urgency: "urgent" | "normal" | "low";
  status: "pending" | "approved" | "rejected";
  created_at: string;
  resolved_at?: string;
  resolved_by?: string;
}

export interface ActivityEvent {
  id: string;
  agent_id: string;
  event_type: string;
  description: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface ApprovalListResponse {
  approvals: ApprovalRequest[];
  total: number;
}

export interface ActivityListResponse {
  events: ActivityEvent[];
  total: number;
}
