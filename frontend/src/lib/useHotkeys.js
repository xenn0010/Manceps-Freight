import { useEffect } from "react";
import { useStore } from "../store/useStore";
import { demoScript } from "../services";

const isTyping = (el) => el && (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable);
const overlayOpen = () => document.querySelector('[role="alertdialog"], [role="dialog"], [data-radix-popper-content-wrapper]');

export function useHotkeys() {
  useEffect(() => {
    const onKey = (e) => {
      const s = useStore.getState();
      if (e.key === "Escape") {
        if (isTyping(e.target)) return e.target.blur();
        if (overlayOpen()) return;
        if (s.ui.panel || s.ui.selectedTruckId) s.closePanel();
        return;
      }
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || overlayOpen()) return;
      if (e.shiftKey && e.key === "R") {
        e.preventDefault();
        s.setTransient({ resetOpen: true });
      } else if (!e.shiftKey && (e.key === "n" || e.key === "ArrowRight")) {
        if (e.key === "ArrowRight" && e.target.closest?.(".maplibregl-map")) return;
        e.preventDefault();
        demoScript.next();
      } else if (!e.shiftKey && e.key === "d") {
        s.setTransient({ demoOpen: !s.transient.demoOpen });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
