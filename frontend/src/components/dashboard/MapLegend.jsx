const Line = ({ kind }) => (
  <svg width="30" height="8" aria-hidden="true">
    {kind === "confirmed" && <line x1="2" y1="4" x2="28" y2="4" stroke="#3A3D42" strokeWidth="3" strokeLinecap="round" />}
    {kind === "proposed" && <line x1="2" y1="4" x2="28" y2="4" stroke="#AF6EFF" strokeWidth="3" strokeDasharray="6 4" />}
    {kind === "empty" && <line x1="3" y1="4" x2="28" y2="4" stroke="#9A9DA4" strokeWidth="3" strokeDasharray="0.1 6" strokeLinecap="round" />}
  </svg>
);

export function MapLegend() {
  return (
    <div className="grid grid-cols-[auto_auto] gap-x-4 gap-y-1.5 rounded-[14px] bg-white/85 px-3 py-2.5 text-[11.5px] text-[#3f4247] shadow-sm backdrop-blur" data-testid="map-legend">
      <span className="flex items-center gap-1.5" data-testid="legend-confirmed"><Line kind="confirmed" /> Confirmed</span>
      <span className="flex items-center gap-1.5" data-testid="legend-proposed"><Line kind="proposed" /> Proposed</span>
      <span className="flex items-center gap-1.5" data-testid="legend-empty"><Line kind="empty" /> Empty repositioning</span>
      <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-[#3A3D42] bg-white" /> Pickup</span>
      <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-white bg-[#3A3D42] shadow-[0_0_0_1px_rgba(0,0,0,0.08)]" /> Delivery</span>
      <span className="flex items-center gap-1.5">
        <svg width="14" height="14" viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="17" fill="#fff" stroke="#181A1A" strokeWidth="4" /><rect x="17" y="15" width="10" height="16" rx="2" fill="#181A1A" /></svg>
        Truck now
      </span>
    </div>
  );
}
