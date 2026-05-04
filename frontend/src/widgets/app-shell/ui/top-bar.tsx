"use client";

import { Fragment } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useSession, signOut } from "next-auth/react";
import { useLocale, useTranslations } from "next-intl";
import { Sun, Moon, LogOut, User, Bell } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Separator } from "@/shared/ui/separator";
import { SidebarTrigger } from "@/shared/ui/sidebar";
import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/shared/ui/breadcrumb";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import { LocaleSwitcher } from "./locale-switcher";

const segmentLabels: Record<string, string> = {
  home: "Home",
  activity: "Activity",
  approvals: "Approvals",
  agents: "Fleet",
  analytics: "Analytics",
  cost: "Cost & Usage",
  dashboard: "Dashboard",
  requirements: "Requirements",
  ingest: "Ingest",
  questions: "Questions",
  monitor: "Monitor",
  messages: "Messages",
  settings: "Settings",
};

// Mock: number of unread notifications
const UNREAD_NOTIFICATION_COUNT = 3;

export function TopBar() {
  const { theme, setTheme } = useTheme();
  const { data: session } = useSession();
  const t = useTranslations("auth");
  const tc = useTranslations("common");
  const locale = useLocale();
  const pathname = usePathname();

  const userName = session?.user?.name || "";
  const userInitial = userName.charAt(0).toUpperCase() || "U";

  // Derive breadcrumb segments from pathname, excluding the locale prefix
  const segments = pathname.split("/").filter(Boolean);
  const pathSegments = segments.slice(1); // remove locale segment

  const hasNotifications = UNREAD_NOTIFICATION_COUNT > 0;

  return (
    <header className="flex h-14 items-center gap-2 border-b px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mx-1 h-5" />

      {pathSegments.length > 0 && (
        <Breadcrumb>
          <BreadcrumbList>
            {pathSegments.map((segment, index) => {
              const label = segmentLabels[segment] || segment;
              const href = `/${locale}/${pathSegments.slice(0, index + 1).join("/")}`;
              const isLast = index === pathSegments.length - 1;

              return isLast ? (
                <BreadcrumbItem key={`${segment}-${index}`}>
                  <BreadcrumbPage>{label}</BreadcrumbPage>
                </BreadcrumbItem>
              ) : (
                <Fragment key={`${segment}-${index}`}>
                  <BreadcrumbItem>
                    <BreadcrumbLink asChild>
                      <Link href={href}>{label}</Link>
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                </Fragment>
              );
            })}
          </BreadcrumbList>
        </Breadcrumb>
      )}

      <div className="flex-1" />

      <Button variant="ghost" size="icon" className="relative">
        <Bell className="size-4" />
        {hasNotifications && (
          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500" />
        )}
        <span className="sr-only">Notifications</span>
      </Button>

      <LocaleSwitcher />
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      >
        <Sun className="size-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute size-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        <span className="sr-only">{tc("toggleTheme")}</span>
      </Button>
      {session?.user && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="rounded-full">
              <Avatar size="sm">
                <AvatarFallback>{userInitial}</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel className="flex items-center gap-2">
              <User className="size-4" />
              <span>{userName}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => signOut({ callbackUrl: `/${locale}/login` })}
            >
              <LogOut className="mr-2 size-4" />
              {t("logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </header>
  );
}
