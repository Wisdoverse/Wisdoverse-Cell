"use client";

import { signOut, useSession } from "next-auth/react";
import { useTheme } from "next-themes";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { Languages, LogOut, MonitorCog, ShieldCheck, UserCircle } from "lucide-react";

import { locales } from "@/i18n/config";
import type { UserRole } from "@/lib/auth/roles";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { Separator } from "@/shared/ui/separator";
import { PageHeader } from "@/shared/ui/page-header";

const localeLabels: Record<string, string> = {
  zh: "中文",
  en: "English",
  ja: "日本語",
};

const roleLabelKeys: Record<UserRole, string> = {
  admin: "roleAdmin",
  manager: "roleManager",
  viewer: "roleViewer",
};

function formatRole(role: string | undefined, t: (key: string) => string) {
  if (!role) return null;
  if (role in roleLabelKeys) return t(roleLabelKeys[role as UserRole]);
  return role.replace(/[_-]/g, " ");
}

export function SettingsPageWidget() {
  const { data: session } = useSession();
  const { theme, setTheme } = useTheme();
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("settings");
  const tc = useTranslations("common");

  function onLocaleChange(newLocale: string) {
    const segments = pathname.split("/");
    segments[1] = newLocale;
    router.push(segments.join("/"));
  }

  const userName = session?.user?.name || tc("noData");
  const userEmail = session?.user?.email || tc("noData");
  const userRole = formatRole(session?.user?.role, t) || tc("noData");

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserCircle className="text-muted-foreground size-5" />
              {t("account")}
            </CardTitle>
            <CardDescription>{t("accountDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1">
                <p className="text-muted-foreground text-xs font-medium uppercase">{t("name")}</p>
                <p className="truncate text-sm font-medium">{userName}</p>
              </div>
              <div className="space-y-1">
                <p className="text-muted-foreground text-xs font-medium uppercase">{t("email")}</p>
                <p className="truncate text-sm font-medium">{userEmail}</p>
              </div>
              <div className="space-y-1">
                <p className="text-muted-foreground text-xs font-medium uppercase">{t("role")}</p>
                <Badge variant="secondary" className="text-left whitespace-normal">
                  {userRole}
                </Badge>
              </div>
            </div>

            <Separator />

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <ShieldCheck className="text-muted-foreground size-5" />
                <div>
                  <p className="text-sm font-medium">{t("session")}</p>
                  <p className="text-muted-foreground text-sm">{t("sessionActive")}</p>
                </div>
              </div>
              <Button
                variant="outline"
                onClick={() => signOut({ callbackUrl: `/${locale}/login` })}
              >
                <LogOut className="size-4" />
                {t("signOut")}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MonitorCog className="text-muted-foreground size-5" />
              {t("preferences")}
            </CardTitle>
            <CardDescription>{t("preferencesDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-2">
              <Label htmlFor="settings-theme">{t("theme")}</Label>
              <Select value={theme ?? "system"} onValueChange={setTheme}>
                <SelectTrigger id="settings-theme" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="system">{t("themeSystem")}</SelectItem>
                  <SelectItem value="light">{t("themeLight")}</SelectItem>
                  <SelectItem value="dark">{t("themeDark")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="settings-language" className="flex items-center gap-2">
                <Languages className="text-muted-foreground size-4" />
                {t("language")}
              </Label>
              <Select value={locale} onValueChange={onLocaleChange}>
                <SelectTrigger id="settings-language" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {locales.map((loc) => (
                    <SelectItem key={loc} value={loc}>
                      {localeLabels[loc]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
