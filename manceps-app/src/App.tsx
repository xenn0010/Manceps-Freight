import { useEffect } from "react";
import { driverFirst, startUiRuntime } from "./actions";
import { startDemoRuntime } from "./demo";
import { bootSession } from "./live/session";
import { fmtClock } from "./logic/derive";
import { getMap } from "./map/registry";
import { useAppState } from "./store";
import { AddTruckPanel } from "./components/AddTruckPanel";
import { ChatPanel } from "./components/ChatPanel";
import { AskPill, Toast } from "./components/Dock";
import { FleetBoard } from "./components/FleetBoard";
import { Header } from "./components/Header";
import { ImportPanel } from "./components/ImportPanel";
import { MapView } from "./components/MapView";
import { MePanel } from "./components/MePanel";
import { NeedCard } from "./components/NeedCard";
import { PermPanel } from "./components/PermPanel";
import { SheetView } from "./components/SheetView";
import { SignIn } from "./components/SignIn";
import { RING_S, TruckPanel } from "./components/TruckPanel";
import { usePage } from "./pages/usePage";

/** Keep the bubble over the truck in sync while the user is on a call. */
function useYouCallBubble(): void {
  const s = useAppState();
  useEffect(() => {
    const c = s.call;
    if (!c || c.mode !== "you") return;
    const el = Math.floor((Date.now() - c.t0) / 1000);
    const who = el >= RING_S ? "On call with you · " + fmtClock(el - RING_S) : "Calling " + driverFirst(c.id) + "…";
    getMap()?.say(c.id, { mode: "you", who, text: "" });
  }, [s.call, s.tick]);
}

/** The signed-in dispatch screen: map, header, side panels, sheet and the agent's dock. */
function Dispatch(): JSX.Element {
  const s = useAppState();
  useEffect(() => { const ui = startUiRuntime(), demo = startDemoRuntime(); return () => { ui(); demo(); }; }, []);
  useYouCallBubble();
  const sheet = s.view === "sheet";
  return (
    <div data-screen-label="Dispatch map" style={{ position: "fixed", inset: 0 }}>
      <MapView />
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "radial-gradient(55% 45% at 12% 88%,rgba(34,114,173,.16),transparent 70%),radial-gradient(45% 40% at 92% 8%,rgba(76,155,255,.14),transparent 70%)" }} />
      <div style={{ position: "absolute", inset: "0 0 auto 0", height: 140, pointerEvents: "none", background: "linear-gradient(180deg,rgba(244,246,249,.9),rgba(244,246,249,0))" }} />
      <div style={{ position: "absolute", inset: "auto 0 0 0", height: 200, pointerEvents: "none", background: "linear-gradient(0deg,rgba(244,246,249,.9),rgba(244,246,249,0))" }} />
      <Header />
      {s.me && <MePanel />}
      {sheet && <SheetView />}
      <div style={{ position: "absolute", left: 20, top: 88, display: "flex", flexDirection: "column", gap: 12, pointerEvents: "none" }}>
        <NeedCard />
        <FleetBoard />
      </div>
      {s.sel && <TruckPanel id={s.sel} />}
      <Toast />
      {!s.chat && !s.permOpen && !sheet && <AskPill />}
      {s.chat && !s.permOpen && !sheet && <ChatPanel />}
      {s.permOpen && <PermPanel />}
      {s.panel === "addTruck" && <AddTruckPanel />}
      {s.panel === "import" && <ImportPanel />}
    </div>
  );
}

/** /app: phone sign-in gate in front of the dispatch screen. */
export function App(): JSX.Element {
  usePage("Manceps — Dispatch", "page-app");
  const session = useAppState().session;
  useEffect(() => { void bootSession(); }, []);
  if (session === "booting") return <div aria-busy="true" style={{ position: "fixed", inset: 0, background: "#F4F6F9" }} />;
  if (session !== "ready") return <SignIn />;
  return <Dispatch />;
}
