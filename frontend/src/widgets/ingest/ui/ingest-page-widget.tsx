"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { IngestResult } from "@/components/ingest/ingest-result";
import { UploadForm } from "@/components/ingest/upload-form";
import { PageHeader } from "@/shared/ui/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import type { IngestResponse } from "@/lib/api/types";

export function IngestPageWidget() {
  const t = useTranslations("ingest");
  const [result, setResult] = useState<IngestResponse | null>(null);

  if (result) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("title")} />
        <IngestResult result={result} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      <Tabs defaultValue="upload">
        <TabsList>
          <TabsTrigger value="upload">{t("uploadTab")}</TabsTrigger>
          <TabsTrigger value="wechat">{t("wechatTab")}</TabsTrigger>
        </TabsList>
        <TabsContent value="upload" className="mt-4">
          <UploadForm source="manual" onSuccess={setResult} />
        </TabsContent>
        <TabsContent value="wechat" className="mt-4">
          <UploadForm source="wechat" onSuccess={setResult} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
