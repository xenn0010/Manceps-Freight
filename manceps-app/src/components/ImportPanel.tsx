import { useEffect, useRef, useState } from "react";
import { showToast } from "../actions";
import { imports } from "../api";
import { friendlyMessage } from "../api/errors";
import type { DuplicateStrategy, ImportOut, PreviewOut } from "../api/types";
import { reloadFleet } from "../live/fleet";
import { initialMapping, waitForImport, type AppImportEntity } from "../live/imports";
import { setState } from "../store";
import { ChooseStep, DoneStep, MappingStep, PreviewStep } from "./ImportSteps";
import { Modal } from "./Modal";

export type ImportStep = "choose" | "mapping" | "preview" | "done";

export interface ImportCtl {
  step: ImportStep;
  entity: AppImportEntity;
  imp: ImportOut | null;
  mapping: Record<string, string | null>;
  preview: PreviewOut | null;
  strategy: DuplicateStrategy;
  busy: string | null;
  error: string | null;
  setEntity: (e: AppImportEntity) => void;
  setMapping: (m: Record<string, string | null>) => void;
  upload: (file: File) => void;
  saveMapping: () => void;
  changeStrategy: (s: DuplicateStrategy) => void;
  commit: () => void;
  undo: () => void;
  editMapping: () => void;
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

/**
 * Commit an import, wait for the worker to finish it, then reload the fleet.
 *
 * Args:
 *   id: Import id.
 *   strategy: How to treat rows matching existing records.
 *   progress: Receives progress text while the worker runs.
 *
 * Returns:
 *   The settled import (committed or failed).
 */
async function commitAndWait(id: string, strategy: DuplicateStrategy, progress: (t: string) => void): Promise<ImportOut> {
  const started = await imports.commit(id, strategy);
  const done = await waitForImport(imports.get, started.id, sleep, (x) => progress("Importing… " + (x.progress ? x.progress.done + " of " + x.progress.total : "")));
  await reloadFleet();
  return done;
}

/** State and actions for one import: upload -> mapping -> preview -> commit -> (undo). */
function useImport(): ImportCtl {
  const [step, setStep] = useState<ImportStep>("choose");
  const [entity, setEntity] = useState<AppImportEntity>("carriers");
  const [imp, setImp] = useState<ImportOut | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const [strategy, setStrategy] = useState<DuplicateStrategy>("update");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  const run = async (label: string, fn: () => Promise<void>): Promise<void> => {
    setBusy(label); setError(null);
    try { await fn(); } catch (e) { if (alive.current) setError(e instanceof Error && !("code" in e) ? e.message : friendlyMessage(e)); }
    if (alive.current) setBusy(null);
  };
  const toPreview = async (i: ImportOut, s: DuplicateStrategy): Promise<void> => {
    setPreview(await imports.preview(i.id, s));
    setStep("preview");
  };
  const settle = async (i: ImportOut): Promise<void> => {
    const done = i.status === "validating" ? await waitForImport(imports.get, i.id, sleep) : i;
    setImp(done);
    setMapping(initialMapping(done));
    if (done.status === "uploaded") setStep("mapping");
    else if (done.status === "mapped") await toPreview(done, strategy);
    else if (done.status === "failed") throw new Error(done.error ?? "The import failed.");
    else { setStep("done"); }
  };
  return {
    step, entity, imp, mapping, preview, strategy, busy, error, setEntity, setMapping,
    upload: (file) => void run("Uploading " + file.name + "…", async () => settle(await imports.upload(entity, file, file.name, crypto.randomUUID()))),
    saveMapping: () => void run("Checking rows…", async () => { if (imp) await settle(await imports.setMapping(imp.id, mapping)); }),
    changeStrategy: (s) => { setStrategy(s); if (imp) void run("Updating preview…", () => toPreview(imp, s)); },
    editMapping: () => setStep("mapping"),
    commit: () => void run("Importing…", async () => {
      if (!imp) return;
      setImp(await commitAndWait(imp.id, strategy, setBusy));
      setStep("done");
    }),
    undo: () => void run("Undoing…", async () => {
      if (!imp) return;
      const done = await waitForImport(imports.get, (await imports.undo(imp.id)).id, sleep);
      setImp(done);
      await reloadFleet();
      showToast("Import undone");
    }),
  };
}

/** Import carriers or drivers from a CSV or Excel file. */
export function ImportPanel(): JSX.Element {
  const c = useImport();
  return (
    <Modal title="Import from a spreadsheet" width={640} onClose={() => setState({ panel: null })}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {c.step === "choose" && <ChooseStep c={c} />}
        {c.step === "mapping" && <MappingStep c={c} />}
        {c.step === "preview" && <PreviewStep c={c} />}
        {c.step === "done" && <DoneStep c={c} />}
        {c.busy && <span role="status" style={{ fontSize: 13, color: "#1B5E94" }}>{c.busy}</span>}
        {c.error && <span role="alert" style={{ fontSize: 13, color: "#B23A31" }}>{c.error}</span>}
      </div>
    </Modal>
  );
}
