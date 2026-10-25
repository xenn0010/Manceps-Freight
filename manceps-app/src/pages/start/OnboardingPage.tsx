import { useCallback, useEffect, useRef, useState } from "react";
import { initialOnboard, type OnboardState } from "../../logic/onboarding";
import { usePage } from "../usePage";
import { BUILD } from "./content";
import { Home } from "./Home";
import { Questions } from "./Questions";
import { Building, Signup } from "./Signup";
import type { SetOnboard } from "./shared";

/** Time per "building" message. */
const BUILD_STEP_MS = 800;

/** Sign-up, five questions, a short build animation, then the setup guide. */
export function OnboardingPage(): JSX.Element {
  usePage("Manceps — Set up your dispatch", "page-start");
  const [s, setS] = useState<OnboardState>(initialOnboard);
  const timer = useRef<number | undefined>(undefined);
  const set: SetOnboard = useCallback((patch) => setS((x) => ({ ...x, ...(typeof patch === "function" ? patch(x) : patch) })), []);
  useEffect(() => () => window.clearInterval(timer.current), []);
  const build = (): void => {
    set({ stage: "building", bi: 0 });
    let k = 0;
    window.clearInterval(timer.current);
    timer.current = window.setInterval(() => {
      k++;
      if (k >= BUILD.length) { window.clearInterval(timer.current); set({ stage: "home" }); }
      else set({ bi: k });
    }, BUILD_STEP_MS);
  };
  if (s.stage === "signup") return <Signup s={s} set={set} />;
  if (s.stage === "q") return <Questions s={s} set={set} build={build} />;
  if (s.stage === "building") return <Building s={s} set={set} />;
  return <Home s={s} set={set} />;
}
