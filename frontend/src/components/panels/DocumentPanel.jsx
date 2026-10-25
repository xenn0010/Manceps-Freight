import { CheckCircle2, FileText, XCircle } from "lucide-react";
import { useStore } from "../../store/useStore";
import { stamp } from "../../lib/format";
import { Pill } from "../common/ui";
import { PanelShell } from "./PanelShell";

export default function DocumentPanel({ id }) {
  const doc = useStore((s) => s.data.documents[id]);
  if (!doc) return null;
  return (
    <PanelShell testid="document-panel" eyebrow={`Document · ${doc.from}`} title={doc.title} simulated="Demo data">
      <div className="flex items-center gap-3 rounded-[18px] bg-white/85 p-3.5 ring-1 ring-[#181A1A]/[0.05]">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#AF6EFF]/15 text-[#7A35DB]"><FileText className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium">{doc.fileName}</div>
          <div className="text-[11.5px] text-[#6B6F76] tnum">Received {stamp(doc.receivedAt)} · {doc.from}</div>
        </div>
        <Pill tone={doc.status === "signed" ? "green" : "grey"} data-testid="document-status">{doc.status === "signed" ? "Signed" : "Received"}</Pill>
      </div>
      <div className={`flex items-center gap-2 rounded-[14px] px-3.5 py-2.5 text-[13px] font-medium ${doc.matches ? "bg-[#A1E688]/35" : "bg-[#E5484D]/10 text-[#C2282D]"}`} data-testid="document-terms-match">
        {doc.matches ? <CheckCircle2 className="h-4 w-4 text-[#2C6A18]" /> : <XCircle className="h-4 w-4" />} {doc.kind === "pod" ? "Proof of delivery received" : doc.matches ? "Written terms match offer" : "Written terms differ"}
      </div>
      <div className="rounded-[18px] bg-white p-5 shadow-[0_10px_30px_-18px_rgba(24,26,26,0.35)] ring-1 ring-[#181A1A]/[0.06]" data-testid="document-sheet">
        <div className="flex items-start justify-between border-b border-dashed border-[#181A1A]/15 pb-3">
          <div>
            <div className="text-[15px] font-semibold tracking-tight">{doc.kind === "pod" ? "PROOF OF DELIVERY" : "RATE CONFIRMATION"}</div>
            <div className="text-[11.5px] text-[#6B6F76]">{doc.from} · Load O-1 · Carrier: Demo West Freight</div>
          </div>
          <span className="text-[11px] text-[#9A9DA4]">p. 1 / 1</span>
        </div>
        <table className="mt-3 w-full text-[12.5px] tnum">
          <thead><tr className="text-left text-[11px] text-[#6B6F76]"><th className="pb-1 font-medium">Term</th><th className="pb-1 font-medium">Written</th>{doc.kind !== "pod" && <th className="pb-1 font-medium">Offer</th>}<th /></tr></thead>
          <tbody>
            {doc.fields.map((f) => (
              <tr key={f.label} className="border-t border-[#181A1A]/[0.05]">
                <td className="py-1.5 pr-2 text-[#4B4F55]">{f.label}</td>
                <td className="py-1.5 pr-2 font-medium">{f.written}</td>
                {doc.kind !== "pod" && <td className="py-1.5 pr-2 text-[#6B6F76]">{f.offer}</td>}
                <td className="py-1.5">{doc.kind === "pod" || f.offer === f.written ? <CheckCircle2 className="h-3.5 w-3.5 text-[#4E9A33]" /> : <XCircle className="h-3.5 w-3.5 text-[#C2282D]" data-testid="document-field-mismatch" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex justify-between text-[11px] text-[#9A9DA4]">
          <span>Broker signature: {doc.status === "signed" ? "Maya Lin ✓" : "pending"}</span>
          <span>Simulated document</span>
        </div>
      </div>
    </PanelShell>
  );
}
