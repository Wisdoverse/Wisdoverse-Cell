"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { CompanyKnowledgePanel } from "@/features/company-knowledge";
import { CompanyTemplatePanel } from "@/features/company-template-management";
import { Input } from "@/shared/ui/input";
import { PageHeader } from "@/shared/ui/page-header";

export function CompanyGovernancePage() {
  const t = useTranslations("companyGovernance");
  const [companyId, setCompanyId] = useState("");

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <div className="max-w-md space-y-2">
        <label htmlFor="governance-company-id" className="text-sm font-medium">{t("companyId")}</label>
        <Input id="governance-company-id" value={companyId} onChange={(event) => setCompanyId(event.target.value)} placeholder={t("companyIdPlaceholder")} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <CompanyTemplatePanel companyId={companyId.trim()} />
        <CompanyKnowledgePanel companyId={companyId.trim()} />
      </div>
    </div>
  );
}
