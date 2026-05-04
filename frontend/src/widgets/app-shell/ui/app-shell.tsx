import { AppSidebar } from "@/components/layout/app-sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { SidebarInset, SidebarProvider } from "@/shared/ui/sidebar";
import { EventListener } from "./event-listener";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <TopBar />
        <main className="flex-1 p-6 animate-fade-in">{children}</main>
      </SidebarInset>
      <EventListener />
    </SidebarProvider>
  );
}
