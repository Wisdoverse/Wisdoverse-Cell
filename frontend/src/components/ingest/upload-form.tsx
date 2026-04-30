"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { uploadContent } from "@/lib/api/ingest";
import type { IngestResponse } from "@/lib/api/types";

interface UploadFormProps {
  source: string;
  onSuccess: (result: IngestResponse) => void;
}

export function UploadForm({ source, onSuccess }: UploadFormProps) {
  const t = useTranslations("ingest");
  const tc = useTranslations("common");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [context, setContext] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;

    setLoading(true);
    try {
      const result = await uploadContent({
        source,
        content: content.trim(),
        title: title.trim() || null,
        context: context.trim() || null,
      });
      onSuccess(result);
    } catch (err) {
      console.error("[upload-form] Upload failed:", err);
      toast.error(tc("error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="title">{t("titleField")}</Label>
        <Input
          id="title"
          placeholder={t("titlePlaceholder")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="content">{t("contentField")}</Label>
        <Textarea
          id="content"
          placeholder={t("contentPlaceholder")}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={10}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="context">{t("contextField")}</Label>
        <Textarea
          id="context"
          placeholder={t("contextPlaceholder")}
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={3}
        />
      </div>

      <Button type="submit" disabled={loading || !content.trim()}>
        {loading ? tc("loading") : t("submit")}
      </Button>
    </form>
  );
}
