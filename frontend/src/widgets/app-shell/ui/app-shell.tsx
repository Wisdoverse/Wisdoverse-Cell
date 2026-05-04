import { SidebarInset, SidebarProvider } from "@/shared/ui/sidebar";
import { AppSidebar } from "./app-sidebar";
import { EventListener } from "./event-listener";
import { TopBar } from "./top-bar";

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
