import { redirect } from "next/navigation";

import { isBootstrapSetupRequiredForLogin } from "@/lib/auth/bootstrap-admin";

import { LoginPageWidget } from "./login-page-widget";

export type LoginRouteWidgetProps = {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{ callbackUrl?: string | string[] }>;
};

export async function LoginRouteWidget({
  params,
  searchParams,
}: LoginRouteWidgetProps) {
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
