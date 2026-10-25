import { useEffect } from "react";
import { Toaster } from "sonner";
import { useStore } from "./store/useStore";
import { startSimulation } from "./services";
import { useHotkeys } from "./lib/useHotkeys";
import { TopBar } from "./components/shell/TopBar";
import { ResetDialog } from "./components/shell/ResetDialog";
import { FeedbackDialog } from "./components/shell/FeedbackDialog";
import Dashboard from "./pages/Dashboard";
import FleetPage from "./pages/Fleet";
import { RecordDrawer } from "./components/fleet/RecordDrawer";
import { IntakeDialog } from "./components/fleet/IntakeDialog";
import { AiSettingsSheet } from "./components/shell/AiSettingsSheet";
import { CallConfirmCard } from "./components/shell/CallConfirmCard";
import { liveCallService } from "./services";

function App() {
  const view = useStore((s) => s.ui.view);
  useHotkeys();
  useEffect(() => {
    startSimulation();
    liveCallService.resume();
  }, []);
  return (
    <div className="h-screen flex flex-col px-5 pb-4 overflow-hidden" data-testid="app-shell">
      <TopBar />
      {view === "fleet" ? <FleetPage /> : <Dashboard />}
      <ResetDialog />
      <FeedbackDialog />
      <RecordDrawer />
      <IntakeDialog />
      <AiSettingsSheet />
      <CallConfirmCard />
      <Toaster
        position="bottom-center"
        offset={92}
        toastOptions={{
          className: "!rounded-2xl !border-white/90 !bg-white/90 !backdrop-blur-xl !shadow-[0_18px_40px_-18px_rgba(24,26,26,0.35)] !font-[inherit]",
        }}
      />
    </div>
  );
}

export default App;
