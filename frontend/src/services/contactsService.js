// Contact lookup seam: replace with the broker/shipper database when it lands.
export const BROKERS = [
  { id: "BRK-PACIFIC", name: "Maya Lin", company: "Demo Pacific Broker", role: "broker" },
  { id: "BRK-DESERT", name: "Dispatch desk", company: "Desert Line Logistics", role: "broker" },
  { id: "BRK-CENTRAL", name: "Luis Romero", company: "Central Valley Brokers", role: "broker" },
];

export const contactsService = {
  list(data) {
    const drivers = Object.values(data.drivers).map((d) => ({ id: d.id, name: d.name, role: "driver", company: data.carrier.name, truckId: d.truckId }));
    return [...drivers, ...BROKERS].map((c) => ({ ...c, phone: data.calling?.numbers?.[c.id] || "" }));
  },
  get(data, id) {
    return this.list(data).find((c) => c.id === id) || null;
  },
  find(data, text) {
    const q = (text || "").toLowerCase();
    const list = this.list(data);
    const unit = /(\d{3,4})/.exec(q)?.[1];
    return (
      list.find((c) => q.includes(c.name.toLowerCase())) ||
      list.find((c) => c.role === "driver" && q.includes(c.name.split(" ")[0].toLowerCase())) ||
      list.find((c) => c.company && q.includes(c.company.toLowerCase().split(" ")[0])) ||
      (unit && list.find((c) => c.role === "driver" && data.trucks[c.truckId]?.unit === unit)) ||
      (/broker/.test(q) && /102|stockton|appointment|window/.test(q) && list.find((c) => c.id === "BRK-CENTRAL")) ||
      (/broker/.test(q) && list.find((c) => c.id === "BRK-PACIFIC")) ||
      null
    );
  },
};
