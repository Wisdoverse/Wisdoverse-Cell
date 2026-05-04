"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { MessageSearch } from "./message-search";
import { MessageTable } from "./message-table";
import { PageHeader } from "@/shared/ui/page-header";
import { searchMessages } from "@/lib/api/messages";
import type { MessageSearchParams, MessageSearchResult } from "@/lib/api/types";

export function MessagesPageWidget() {
  const t = useTranslations("messages");
  const tc = useTranslations("common");
  const [params, setParams] = useState<MessageSearchParams>({});
  const [results, setResults] = useState<MessageSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch() {
    setIsLoading(true);
    setHasSearched(true);
    try {
      const data = await searchMessages(params);
      setResults(data);
    } catch (err) {
      console.error("[messages] Search failed:", err);
      toast.error(tc("error"));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      <MessageSearch
        params={params}
        onChange={setParams}
        onSearch={handleSearch}
        isLoading={isLoading}
      />
      {hasSearched && <MessageTable data={results} isLoading={isLoading} />}
    </div>
  );
}
