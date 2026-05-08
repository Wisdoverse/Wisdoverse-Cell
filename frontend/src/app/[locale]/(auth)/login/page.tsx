import { redirect } from "next/navigation";

import { isBootstrapSetupRequiredForLogin } from "@/lib/auth/bootstrap-admin";
import { LoginPageWidget } from "@/widgets/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type LoginRouteProps = {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{ callbackUrl?: string | string[] }>;
};

export default async function LoginRoute({ params, searchParams }: LoginRouteProps) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (await isBootstrapSetupRequiredForLogin()) {
    const callbackUrl = Array.isArray(query?.callbackUrl)
      ? query?.callbackUrl[0]
      : query?.callbackUrl;
    const setupUrl = new URL(`http://localhost/${locale}/setup`);
    if (callbackUrl) {
      setupUrl.searchParams.set("callbackUrl", callbackUrl);
    }
    redirect(`${setupUrl.pathname}${setupUrl.search}`);
  }

  return <LoginPageWidget />;
}
