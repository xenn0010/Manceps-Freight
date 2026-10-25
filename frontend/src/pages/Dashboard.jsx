import { KpiRow } from "../components/dashboard/KpiRow";
import { TruckStrip } from "../components/dashboard/TruckStrip";
import { MapCanvas } from "../components/dashboard/MapCanvas";
import { CommandBar } from "../components/dashboard/CommandBar";
import { RightPanel } from "../components/panels/RightPanel";

export default function Dashboard() {
  return (
    <main className="flex min-h-0 flex-1 flex-col gap-3" data-testid="dashboard-page">
      <KpiRow />
      <TruckStrip />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <MapCanvas />
          <CommandBar />
        </div>
        <RightPanel />
      </div>
    </main>
  );
}
