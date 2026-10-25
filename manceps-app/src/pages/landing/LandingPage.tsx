import { usePage } from "../usePage";
import { Hero } from "./Hero";
import { AgentSection, Cta, Dispatchers, HowItWorks } from "./Sections";

/** Marketing site: hero film, how it works, the agent, dispatchers and sign-up CTA. */
export function LandingPage(): JSX.Element {
  usePage("Manceps — AI dispatch for trucking", "page-landing");
  return (
    <>
      <Hero />
      <div style={{ margin: "0 12px", background: "#FFFFFF", borderRadius: 10, overflow: "hidden" }}>
        <HowItWorks />
        <AgentSection />
        <Dispatchers />
      </div>
      <Cta />
    </>
  );
}
