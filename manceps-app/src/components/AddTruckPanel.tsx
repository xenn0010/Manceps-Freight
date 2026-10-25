import { useState, type FormEvent } from "react";
import { showToast } from "../actions";
import { friendlyMessage } from "../api/errors";
import { normalizeUsPhone, typingUsPhone } from "../auth/phone";
import { addTruck, type AddTruckInput, type AddTruckKeys } from "../live/fleet";
import { carrierLabel, equipmentLabel } from "../live/mappers";
import { setState, useAppState } from "../store";
import { Modal } from "./Modal";
import { BTN_OUTLINE, BTN_PRIMARY, FIELD } from "./ui";

/** Equipment the backend accepts (manceps_core/repo/carriers.py EQUIPMENT_TYPES). */
const EQUIPMENT = ["dry_van", "reefer", "flatbed", "step_deck", "power_only", "box_truck", "hotshot"];
const NEW_CARRIER = "__new__";
const LABEL = { display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "#64748A" } as const;

interface Form {
  carrier: string;
  carrierPhone: string;
  carrierName: string;
  unit: string;
  equipment: string;
  plate: string;
  driverName: string;
  driverPhone: string;
}

function newKeys(): AddTruckKeys {
  return { carrier: crypto.randomUUID(), truck: crypto.randomUUID(), driver: crypto.randomUUID() };
}

/**
 * Validate the form into addTruck input.
 *
 * Args:
 *   f: Form values.
 *
 * Returns:
 *   The input, or a message for the user.
 */
function toInput(f: Form): AddTruckInput | string {
  const isNew = f.carrier === NEW_CARRIER;
  const carrierPhone = isNew ? normalizeUsPhone(f.carrierPhone) : null;
  if (isNew && !carrierPhone) return "Enter the carrier's 10-digit US phone number.";
  if (!f.unit.trim()) return "Enter the truck's unit number.";
  const driverPhone = f.driverPhone.trim() ? normalizeUsPhone(f.driverPhone) : null;
  if (f.driverPhone.trim() && !driverPhone) return "Enter the driver's 10-digit US phone number, or leave it blank.";
  if (driverPhone && !f.driverName.trim()) return "Add the driver's name too.";
  return {
    carrierId: isNew ? null : f.carrier,
    newCarrier: isNew && carrierPhone ? { phone: carrierPhone, name: f.carrierName.trim() || null } : null,
    unit: f.unit.trim(), equipment: f.equipment || null, plate: f.plate.trim() || null,
    driverName: f.driverName.trim() || null, driverPhone,
  };
}

/** The form's inputs: carrier (existing or new), truck, and an optional first driver. */
function Fields({ f, put }: { f: Form; put: (patch: Partial<Form>) => void }): JSX.Element {
  const carriers = useAppState().carriers;
  return (
    <>
      <label style={LABEL}>Carrier
        <select value={f.carrier} onChange={(e) => put({ carrier: e.target.value })} style={FIELD}>
          {carriers.map((c) => <option key={c.id} value={c.id}>{carrierLabel(c)}</option>)}
          <option value={NEW_CARRIER}>New carrier…</option>
        </select>
      </label>
      {f.carrier === NEW_CARRIER && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <label style={LABEL}>Carrier phone<input value={f.carrierPhone} inputMode="tel" autoComplete="off" placeholder="(214) 555-0199" onChange={(e) => put({ carrierPhone: typingUsPhone(e.target.value) })} style={FIELD} /></label>
          <label style={LABEL}>Carrier name<input value={f.carrierName} maxLength={200} placeholder="Owner or company" onChange={(e) => put({ carrierName: e.target.value })} style={FIELD} /></label>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <label style={LABEL}>Unit<input value={f.unit} maxLength={200} placeholder="101" onChange={(e) => put({ unit: e.target.value })} style={FIELD} /></label>
        <label style={LABEL}>Equipment
          <select value={f.equipment} onChange={(e) => put({ equipment: e.target.value })} style={FIELD}>
            <option value="">Not set</option>
            {EQUIPMENT.map((q) => <option key={q} value={q}>{equipmentLabel(q)}</option>)}
          </select>
        </label>
        <label style={LABEL}>Plate<input value={f.plate} maxLength={32} placeholder="Optional" onChange={(e) => put({ plate: e.target.value })} style={FIELD} /></label>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <label style={LABEL}>Driver name<input value={f.driverName} maxLength={200} placeholder="Optional" onChange={(e) => put({ driverName: e.target.value })} style={FIELD} /></label>
        <label style={LABEL}>Driver phone<input value={f.driverPhone} inputMode="tel" placeholder="Optional" onChange={(e) => put({ driverPhone: typingUsPhone(e.target.value) })} style={FIELD} /></label>
      </div>
    </>
  );
}

/** Form to add a truck: pick or create its carrier, then unit, equipment, plate and an optional first driver. */
export function AddTruckPanel(): JSX.Element {
  const carriers = useAppState().carriers;
  const [f, setF] = useState<Form>({ carrier: carriers[0]?.id ?? NEW_CARRIER, carrierPhone: "", carrierName: "", unit: "", equipment: "", plate: "", driverName: "", driverPhone: "" });
  const [keys] = useState(newKeys);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const put = (patch: Partial<Form>): void => setF((x) => ({ ...x, ...patch }));
  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    const input = toInput(f);
    if (typeof input === "string") { setError(input); return; }
    setBusy(true); setError(null);
    try {
      const t = await addTruck(input, keys);
      setState({ panel: null });
      showToast("Truck " + t.unit + " added");
    } catch (err) {
      setError(friendlyMessage(err));
      setBusy(false);
    }
  };
  return (
    <Modal title="Add a truck" onClose={() => setState({ panel: null })}>
      <form onSubmit={(e) => void submit(e)} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Fields f={f} put={put} />
        {error && <span role="alert" style={{ fontSize: 13, color: "#B23A31" }}>{error}</span>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" className="hv-ink-border" onClick={() => setState({ panel: null })} style={BTN_OUTLINE}>Cancel</button>
          <button type="submit" className="hv-primary" disabled={busy} style={{ ...BTN_PRIMARY, opacity: busy ? 0.6 : 1 }}>{busy ? "Adding…" : "Add truck"}</button>
        </div>
      </form>
    </Modal>
  );
}
