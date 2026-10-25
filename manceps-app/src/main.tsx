import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { LandingPage } from "./pages/landing/LandingPage";
import { OnboardingPage } from "./pages/start/OnboardingPage";
import "./styles.css";

/** Pages by path; anything unknown shows the landing page. */
const ROUTES: Record<string, () => JSX.Element> = {
  "/": LandingPage,
  "/start": OnboardingPage,
  "/app": App,
};

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element in index.html");
const path = window.location.pathname.replace(/\/+$/, "") || "/";
const Page = ROUTES[path] ?? LandingPage;
createRoot(root).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
