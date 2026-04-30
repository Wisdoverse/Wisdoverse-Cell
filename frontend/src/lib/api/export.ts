import { apiClient } from "./client";
import type { OpenQuestion, PRDExportResponse } from "./types";

export function exportPRD(params?: {
  status?: string;
  format?: string;
}): Promise<PRDExportResponse> {
  return apiClient.get<PRDExportResponse>("/export/prd", params);
}

export function getQuestions(): Promise<OpenQuestion[]> {
  return apiClient.get<OpenQuestion[]>("/questions/open");
}

export function answerQuestion(
  id: string,
  answer: string,
  answeredBy?: string,
): Promise<OpenQuestion> {
  return apiClient.post<OpenQuestion>(`/questions/${id}/answer`, {
    answer,
    answered_by: answeredBy,
  });
}
