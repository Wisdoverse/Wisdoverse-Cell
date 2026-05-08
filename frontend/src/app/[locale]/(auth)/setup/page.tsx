import { redirect } from "next/navigation";

import { hasBootstrapAdmin } from "@/lib/auth/bootstrap-admin";
import { SetupAdminPageWidget } from "@/widgets/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type SetupRouteProps = {
  params: Promise<{ locale: string }>;
};

export default async function SetupRoute({ params }: SetupRouteProps) {
  const { locale } = await params;
  if (await hasBootstrapAdmin()) {
    redirect(`/${locale}/login`);
  }

  return <SetupAdminPageWidget />;
}
