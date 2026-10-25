import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "../../store/useStore";
import TruckPanel from "./TruckPanel";
import DecisionPanel from "./DecisionPanel";
import CallPanel from "./CallPanel";
import ChatPanel from "./ChatPanel";
import MetricPanel from "./MetricPanel";
import ActivityPanel from "./ActivityPanel";
import DocumentPanel from "./DocumentPanel";
import ThreadPanel from "./ThreadPanel";
import RulesPanel from "./RulesPanel";
import LiveCallPanel from "./LiveCallPanel";

const PANELS = { truck: TruckPanel, decision: DecisionPanel, call: CallPanel, chat: ChatPanel, metric: MetricPanel, activity: ActivityPanel, document: DocumentPanel, thread: ThreadPanel, rules: RulesPanel, livecall: LiveCallPanel };

function usePanelWidth() {
  const calc = () => (window.innerWidth >= 1600 ? 440 : 400);
  const [w, setW] = useState(calc);
  useEffect(() => {
    const on = () => setW(calc());
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return w;
}

export function RightPanel() {
  const panel = useStore((s) => s.ui.panel);
  const W = usePanelWidth();
  const Comp = panel && PANELS[panel.type];
  return (
    <motion.aside
      initial={false}
      animate={{ width: Comp ? W + 12 : 0 }}
      transition={{ type: "spring", stiffness: 360, damping: 38 }}
      className="h-full shrink-0 overflow-hidden"
      data-testid="right-panel"
      aria-label="Details"
    >
      <div className="h-full pl-3" style={{ width: W + 12 }}>
        <AnimatePresence mode="wait">
          {Comp && (
            <motion.div key={`${panel.type}-${panel.id}`} className="h-full" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} transition={{ duration: 0.18 }}>
              <Comp id={panel.id} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
