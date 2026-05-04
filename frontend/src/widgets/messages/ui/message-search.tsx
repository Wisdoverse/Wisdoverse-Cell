"use client";

import { useTranslations } from "next-intl";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import type { MessageSearchParams } from "@/lib/api/types";

interface MessageSearchProps {
  params: MessageSearchParams;
  onChange: (params: MessageSearchParams) => void;
  onSearch: () => void;
  isLoading: boolean;
}

export function MessageSearch({
  params,
  onChange,
  onSearch,
  isLoading,
}: MessageSearchProps) {
  const t = useTranslations("messages");
  const tc = useTranslations("common");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSearch();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="space-y-2">
          <Label>{t("content")}</Label>
          <Input
            placeholder={t("searchKeyword")}
            value={params.keyword || ""}
            onChange={(e) => onChange({ ...params, keyword: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label>{t("sender")}</Label>
          <Input
            placeholder={t("sender")}
            value={params.sender_id || ""}
            onChange={(e) => onChange({ ...params, sender_id: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label>{t("timeRange")}</Label>
          <Input
            type="date"
            value={params.start_time || ""}
            onChange={(e) =>
              onChange({ ...params, start_time: e.target.value })
            }
          />
        </div>
        <div className="space-y-2">
          <Label className="invisible">{t("timeRange")}</Label>
          <Input
            type="date"
            aria-label={t("timeRange")}
            value={params.end_time || ""}
            onChange={(e) => onChange({ ...params, end_time: e.target.value })}
          />
        </div>
      </div>
      <Button type="submit" disabled={isLoading}>
        {tc("search")}
      </Button>
    </form>
  );
}
