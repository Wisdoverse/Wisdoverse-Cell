import { apiClient } from "./client";
import type { IngestRequest, IngestResponse } from "./types";

export function uploadContent(data: IngestRequest): Promise<IngestResponse> {
  return apiClient.post<IngestResponse>("/ingest/upload", data);
}
