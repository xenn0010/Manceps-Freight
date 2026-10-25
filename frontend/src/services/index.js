// Service layer: every mock action goes through these modules.
// To plug in a real backend, replace the bodies (keep the signatures) — UI code never touches the engine directly.
export { dispatchService } from "./dispatchService";
export { callService } from "./callService";
export { aiService } from "./aiService";
export { voiceService } from "./voiceService";
export { demoScript, DEMO_STEPS, DEMO_SCENARIOS } from "./demoScript";
export { startSimulation } from "./runtime";
export { exceptionService, executionService, termsService, feedbackService } from "./phase2Services";
export { fleetService, intakeService, settingsService } from "./fleetService";
