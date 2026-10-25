// Everything the app shows that the backend does not serve yet. Each surface that imports from here renders a
// "Demo" tag. To make a surface live, replace its module below with API calls:
//   loads sheet + agent sheet operations -> sheetOps.ts, actions.ts (sheetOp, runSheet)   [/v1/loads, PATCH]
//   needs-your-yes card                  -> derive.ts (allNeeds), actions.ts (book)       [/v1/approvals + decide]
//   dispatch feed toasts                 -> actions.ts (dispatchTick)                      [/v1/events/stream]
//   agent calls, chat answers            -> scripts.ts, actions.ts (startCall, ask)        [agent chat]
//   permissions panel, persona settings  -> data.ts (PRESETS), agentSettings.ts            [agent settings]
//   weekly dashboard numbers             -> derive.ts (weekBars, weekStats, weekTotal)     [/v1/dashboard/summary]
export * from "./actions";
export * from "./agentSettings";
export * from "./data";
export * from "./derive";
export * from "./scripts";
export * from "./sheetOps";
