import { CITIES } from "./cities";
import { EQUIPMENT } from "./fleetFields";
import { normalizePoint, parseWindow } from "./windows";

export const INTAKE_STEPS = [["carrier", "Carrier"], ["truck", "Truck"], ["driver", "Driver"], ["trip", "Commitment"]];

export const EXAMPLES = {
  carrier: ["Add carrier Sierra Haul, contact Sam Park 555-0190, home base Fresno, max deadhead 60 mi"],
  truck: ["Add truck 105, 53' dry van, in Fresno, available Tue 06:00, driver Maria Lopez 555-0142", "Add truck 106 in Stockton"],
  driver: ["Add driver Priya Shah 555-0177, available Tue 08:00, home Stockton"],
  trip: ["Add load L-104 for truck 104, San Jose to Sacramento, pickup Tue 08:00–10:00, delivery Tue 12:00–14:00, $780, broker Bay Produce"],
};

const DAYS = "(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)";
const CITY_ALT = CITIES.join("|");
const grab = (re, text, i = 1) => (re.exec(text) || [])[i] || "";
const cityIn = (s) => CITIES.find((c) => c.toLowerCase() === (s || "").trim().toLowerCase()) || "";
const phoneOf = (t) => grab(/(\(?\d{3}\)?[\s-]?\d{3}-\d{4}|\b\d{3}-\d{4}\b)/, t);
const person = (re, t) => grab(re, t).trim();
const availOf = (t) => (/available\s+now/i.test(t) ? "Now" : normalizePoint(grab(new RegExp(`available\\s+(${DAYS}\\s+\\d{1,2}:\\d{2})`, "i"), t)));
const win = (re, t) => {
  const w = parseWindow(grab(re, t).replace(/\s*-\s*/, "–"));
  return w ? { day: w.day, start: w.start, end: w.end } : { day: "", start: "", end: "" };
};
export const nextTripId = (data) => {
  for (let n = 104; n < 200; n += 1) if (!data.trips[`L-${n}`]) return `L-${n}`;
  return "";
};

const PARSERS = {
  truck: (t) => {
    const eq = grab(/(dry van|reefer|flatbed)/i, t).toLowerCase();
    const avail = availOf(t);
    return {
      unit: grab(/truck\s*#?\s*(\d{3,4})/i, t),
      equipment: EQUIPMENT.find((e) => eq && e.includes(eq)) || EQUIPMENT[0],
      location: cityIn(grab(new RegExp(`\\bin\\s+(${CITY_ALT})`, "i"), t)),
      truckAvailableAt: avail,
      driverName: person(/driver\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)/, t),
      driverPhone: phoneOf(t),
      driverAvailableAt: avail,
    };
  },
  driver: (t, data) => {
    const unit = grab(/truck\s*#?\s*(\d{3,4})/i, t);
    const truck = Object.values(data.trucks).find((x) => x.unit === unit);
    return {
      name: person(/(?:driver|add)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)/, t),
      phone: phoneOf(t),
      truckId: truck ? truck.id : "",
      availableAt: availOf(t),
      homeLocation: cityIn(grab(new RegExp(`(?:home|based in|lives in)\\s+(${CITY_ALT})`, "i"), t)),
    };
  },
  trip: (t, data) => {
    const unit = grab(/truck\s*#?\s*(\d{3,4})/i, t);
    const truck = Object.values(data.trucks).find((x) => x.unit === unit);
    const lane = new RegExp(`(${CITY_ALT})\\s*(?:→|->|to)\\s*(${CITY_ALT})`, "i").exec(t) || [];
    const W = `(${DAYS}\\s+\\d{1,2}:\\d{2}\\s*[–-]\\s*\\d{1,2}:\\d{2})`;
    return {
      id: grab(/\b(L-\d{3})\b/i, t).toUpperCase() || nextTripId(data),
      truckId: truck ? truck.id : "",
      origin: cityIn(lane[1]),
      destination: cityIn(lane[2]),
      pickupWindow: win(new RegExp(`pick\\s*up\\s+${W}`, "i"), t),
      deliveryWindow: win(new RegExp(`deliver(?:y)?\\s+${W}`, "i"), t),
      revenue: grab(/\$\s?([\d,]+)/, t).replace(/,/g, ""),
      broker: grab(/broker\s+([A-Z][\w&' ]*?)(?=,|\.|$)/, t).trim(),
      protected: /protected/i.test(t),
    };
  },
  carrier: (t) => ({
    name: grab(/carrier\s+([A-Z][\w&' ]*?)(?=,|\.|$)/, t).trim(),
    contactName: person(/contact\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)/, t),
    phone: phoneOf(t),
    homeBase: cityIn(grab(new RegExp(`home base\\s+(${CITY_ALT})`, "i"), t)),
    maxDeadhead: grab(/max deadhead\s*(\d+)/i, t) || grab(/(\d+)\s*mi(?:les)?\s+(?:max\s+)?deadhead/i, t) || "75",
    minRatePerMile: grab(/\$(\d+(?:\.\d+)?)\s*\/\s*mi/, t) || "2.20",
  }),
};

export const parseIntake = (kind, text, data) => PARSERS[kind](text, data);
