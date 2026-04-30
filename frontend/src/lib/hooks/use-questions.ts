import useSWR from "swr";
import { getQuestions } from "@/lib/api/export";

export function useQuestions() {
  return useSWR("open-questions", getQuestions);
}
