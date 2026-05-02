"use client";

import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import {
  Home,
  Activity,
  CircleCheck,
  ClipboardList,
  Upload,
  Bot,
  LayoutDashboard,
  DollarSign,
  HeartPulse,
  MessageSquare,
  Settings,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

interface NavItem {
  key: string;
  href: string;
  icon: LucideIcon;
}

interface NavGroup {
  labelKey: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    labelKey: "overview",
    items: [
      { key: "home", href: "/home", icon: Home },
      { key: "activityFeed", href: "/activity", icon: Activity },
    ],
  },
  {
    labelKey: "workflows",
    items: [
      { key: "controlPlane", href: "/workflows", icon: Workflow },
      { key: "approvals", href: "/approvals", icon: CircleCheck },
      { key: "requirements", href: "/requirements", icon: ClipboardList },
      { key: "ingest", href: "/ingest", icon: Upload },
    ],
  },
  {
    labelKey: "agents",
    items: [
      { key: "fleetOverview", href: "/agents", icon: Bot },
    ],
  },
  {
    labelKey: "analytics",
    items: [
      { key: "dashboard", href: "/dashboard", icon: LayoutDashboard },
      { key: "costUsage", href: "/analytics/cost", icon: DollarSign },
      { key: "monitor", href: "/monitor", icon: HeartPulse },
    ],
  },
  {
    labelKey: "system",
    items: [
      { key: "messages", href: "/messages", icon: MessageSquare },
      { key: "settings", href: "/settings", icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const locale = useLocale();

  // Strip locale prefix to compare against nav hrefs
  const pathWithoutLocale = pathname.replace(`/${locale}`, "") || "/";

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1">
          <div className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-md text-sm font-bold">
            P
          </div>
          <span className="text-sm font-semibold">Wisdoverse Cell</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        {navGroups.map((group) => (
          <SidebarGroup key={group.labelKey}>
            <SidebarGroupLabel>{t(group.labelKey)}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const isActive = pathWithoutLocale.startsWith(item.href);
                  return (
                    <SidebarMenuItem key={item.key}>
                      <SidebarMenuButton asChild isActive={isActive} tooltip={t(item.key)}>
                        <Link href={`/${locale}${item.href}`}>
                          <item.icon />
                          <span>{t(item.key)}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}
