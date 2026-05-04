"use client";

import { UploadForm } from "@/features/content-ingest";
import type { IngestResponse } from "@/lib/api/types";
import { toast } from "sonner";

export default function RmIngestWidget() {
  const handleSuccess = (result: IngestResponse) => {
    toast.success(`Extracted ${result.requirements_extracted} requirements`);
  };

  return <UploadForm source="agent-detail" onSuccess={handleSuccess} />;
}
