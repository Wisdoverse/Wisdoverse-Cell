import { LoginRouteWidget, type LoginRouteWidgetProps } from "@/widgets/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function LoginRoute(props: LoginRouteWidgetProps) {
  return <LoginRouteWidget {...props} />;
}
