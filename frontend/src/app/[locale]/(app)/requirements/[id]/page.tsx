"use client";

import { useParams } from "next/navigation";

import { RequirementDetailPageWidget } from "@/widgets/requirements";

export default function RequirementDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <RequirementDetailPageWidget id={id} />;
}
