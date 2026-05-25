import { CommandCenter } from "./command-center";
import { FleetGrid } from "./fleet-grid";
import { PendingApprovals } from "./pending-approvals";
import { RecentActivity } from "./recent-activity";

export function HomePageWidget() {
  return (
    <div className="space-y-8">
      <CommandCenter />
      <PendingApprovals />
      <FleetGrid />
      <RecentActivity />
    </div>
  );
}
