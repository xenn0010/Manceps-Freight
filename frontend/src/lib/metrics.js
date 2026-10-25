const IN_PLAN = ["active", "confirmed"];

export const truckCpm = (data, truckId) => data.trucks[truckId]?.costPerMile ?? data.carrier.costPerMile;

// Plan ledger: active trips, confirmed trips, required repositioning. Optionally previews an offer as booked.
// Each item carries its truck's $/mi so per-truck cost edits flow into the metrics.
export function planLedger(data, previewOffer = null) {
  const items = Object.values(data.trips)
    .filter((t) => IN_PLAN.includes(t.status))
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((t) => ({
      id: t.id, kind: "trip", label: `${t.id} · ${t.origin} → ${t.destination}`,
      revenue: t.revenue, loadedMiles: t.loadedMiles, emptyMiles: t.emptyMiles, cpm: truckCpm(data, t.truckId),
    }));
  Object.values(data.segments)
    .filter((s) => s.status === "planned" && !(previewOffer && s.replacedByOfferId === previewOffer.id))
    .forEach((s) =>
      items.push({
        id: s.id, kind: "segment", label: `Empty return · ${s.origin} → ${s.destination}`,
        revenue: 0, loadedMiles: 0, emptyMiles: s.miles, cpm: truckCpm(data, s.truckId),
      })
    );
  if (previewOffer && !data.trips[previewOffer.tripId]) {
    items.push({
      id: previewOffer.id, kind: "preview", label: `${previewOffer.id} · ${previewOffer.origin} → ${previewOffer.destination} (preview)`,
      revenue: previewOffer.rate, loadedMiles: previewOffer.loadedMiles,
      emptyMiles: previewOffer.emptyToPickup + previewOffer.emptyAfter, cpm: truckCpm(data, previewOffer.truckId),
    });
  }
  return items;
}

export function summarize(items, cpm) {
  const revenue = items.reduce((s, i) => s + i.revenue, 0);
  const emptyMiles = items.reduce((s, i) => s + i.emptyMiles, 0);
  const loadedMiles = items.reduce((s, i) => s + i.loadedMiles, 0);
  const totalMiles = emptyMiles + loadedMiles;
  const cost = Math.round(items.reduce((s, i) => s + (i.loadedMiles + i.emptyMiles) * (i.cpm ?? cpm), 0) * 100) / 100;
  return {
    revenue, emptyMiles, loadedMiles, totalMiles, cost,
    afterCosts: revenue - cost,
    emptyPct: totalMiles ? (emptyMiles / totalMiles) * 100 : 0,
  };
}

export function currentMetrics(data) {
  return summarize(planLedger(data), data.carrier.costPerMile);
}

export function previewMetrics(data, offerId) {
  return summarize(planLedger(data, data.offers[offerId]), data.carrier.costPerMile);
}

export function offerEconomics(offer, segment, cpm) {
  const miles = offer.loadedMiles + offer.emptyToPickup + offer.emptyAfter;
  const cost = miles * cpm;
  const contribution = offer.rate - cost;
  const altCost = segment.miles * cpm;
  const altContribution = -altCost;
  return { miles, cost, contribution, altMiles: segment.miles, altCost, altContribution, delta: contribution - altContribution };
}
