// Copy and demo data for onboarding, verbatim from the design.

/** Icon path data on a 24px grid. */
export const I = {
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M17 3a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3",
  grow: "M3 17l6-6 4 4 8-8M15 7h6v6",
  swap: "M7 4l-4 4 4 4M3 8h14M17 20l4-4-4-4M21 16H7",
  van: "M3 6h12v10H3zM15 9h4l2 3v4h-6M7 19a2 2 0 1 0 0-.01M17 19a2 2 0 1 0 0-.01",
  snow: "M12 2v20M4 6l16 12M20 6L4 18",
  flat: "M2 14h20M5 14v3M19 14v3M7 10h10v4H7z",
  box: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
  map: "M9 4L3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14",
  pin: "M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  route: "M6 19a2 2 0 1 0 0-.01M18 5a2 2 0 1 0 0-.01M6 17V9a4 4 0 0 1 4-4h6M18 7v8a4 4 0 0 1-4 4H8",
  home: "M3 11l9-7 9 7v9H3zM9 20v-6h6v6",
  truck: "M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19a2 2 0 1 0 0-.01M17 19a2 2 0 1 0 0-.01",
  doc: "M6 3h9l4 4v14H6zM14 3v5h5",
  chat: "M4 5h16v11H8l-4 4z",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l2-1-2-4-2 1-2-2V4h-4v2L9 8 7 7 5 11l2 1v2l-2 1 2 4 2-1 2 2v2h4v-2l2-2 2 1 2-4-2-1z",
};

export type CardKey = "who" | "haul" | "lanes";

export type Question =
  | { key: CardKey; type: "cards"; multi: boolean; title: string; sub: string; opts: [string, string, string][] }
  | { key: "agent"; type: "agents"; title: string; sub: string }
  | { key: "name"; type: "name"; title: string; sub: string };

export const QS: Question[] = [
  { key: "who", type: "cards", multi: false, title: "Which best describes your operation?", sub: "We'll tune your dispatcher to how you run.",
    opts: [["Owner-operator", "Just me and my truck", I.user], ["Small fleet", "2–10 trucks", I.users], ["Growing fleet", "11–50 trucks", I.grow], ["Carrier + brokerage", "We move our own and others' freight", I.swap]] },
  { key: "haul", type: "cards", multi: true, title: "What do you haul?", sub: "Pick all that apply.",
    opts: [["Dry van", "53' and 48'", I.van], ["Reefer", "Temperature controlled", I.snow], ["Flatbed", "Step deck, RGN", I.flat], ["Power only", "Drop and hook", I.box]] },
  { key: "lanes", type: "cards", multi: true, title: "Where do your trucks run?", sub: "Your agent searches these lanes first.",
    opts: [["Local", "Under 150 mi from base", I.pin], ["Regional", "West Coast, I-5 and I-80", I.route], ["Long haul", "Cross-country", I.map], ["Dedicated lanes", "Same routes every week", I.swap]] },
  { key: "agent", type: "agents", title: "Pick your dispatcher", sub: "Same work, different voice on the phone with brokers and drivers. Switch anytime." },
  { key: "name", type: "name", title: "Name your company", sub: "This is how your dispatcher introduces you." },
];

export interface Agent {
  id: string;
  name: string;
  role: string;
  img: string;
  blurb: string;
  hello: string;
}

export const AGENTS: Agent[] = [
  { id: "arjun", name: "Arjun Mehta", role: "The Closer", img: "/assets/agent-d.jpg", blurb: "Quick with numbers. Pushes every rate a little further.", hello: "Let's get you paid more." },
  { id: "mei", name: "Mei Lin", role: "The Planner", img: "/assets/agent-c.jpg", blurb: "Thinks three loads ahead. Keeps empty miles low.", hello: "I've already got a plan." },
  { id: "amara", name: "Amara Okafor", role: "The Steady Hand", img: "/assets/agent-b.jpg", blurb: "Calm on bad days. Drivers trust her.", hello: "Don't worry, I've got it." },
  { id: "ethan", name: "Ethan Cole", role: "The Hustler", img: "/assets/agent-a.jpg", blurb: "Always on the boards. First to call on a good load.", hello: "Hey! Ready to roll?" },
];

export const BUILD = ["Creating your workspace", "Teaching your dispatcher your lanes", "Connecting load boards", "Almost loaded"];

export interface ImportSource {
  id: string;
  badge: string;
  title: string;
  sub: string;
  accept: string;
}

export const IMPORTS: ImportSource[] = [
  { id: "wa", badge: "WA", title: "WhatsApp chats", sub: "Driver and broker chats · .txt or .zip", accept: ".txt,.zip" },
  { id: "ct", badge: "VCF", title: "Contacts", sub: "Phone or Google contacts · .vcf or .csv", accept: ".vcf,.csv" },
  { id: "xl", badge: "XLS", title: "Spreadsheets", sub: "Load logs, rate sheets, driver lists · .xlsx or .csv", accept: ".xlsx,.xls,.csv" },
];

export interface Task {
  id: string;
  title: string;
  body: string;
  cta: string;
  /** Image URL, or "AGENT" for the chosen agent's photo. */
  art: string;
  artW: string;
  artR: string;
  optional?: boolean;
  isImport?: boolean;
}

export const TASKS: Task[] = [
  { id: "acct", title: "Create your account", body: "Done. Your workspace is live.", cta: "View settings", art: "/assets/manceps-logo-cut.png", artW: "140px", artR: "0" },
  { id: "import", title: "Import your business", body: "Drop in WhatsApp chats, contacts and spreadsheets. Your dispatcher learns your brokers, drivers and usual rates from them.", cta: "Done importing", isImport: true, art: "AGENT", artW: "96px", artR: "50%" },
  { id: "truck", title: "Add your first truck", body: "Unit number, equipment and driver. Takes 30 seconds, or we'll pull it from your spreadsheet.", cta: "Add truck", art: "/assets/truck-white.png", artW: "170px", artR: "0" },
  { id: "rates", title: "Set your rate floor and lanes", body: "The lowest $/mi your dispatcher may accept, and where it should look. It never books a load or signs a rate con without your one-tap approval.", cta: "Set rate floor", art: "/assets/truck-blue.png", artW: "170px", artR: "0" },
  { id: "phone", title: "Get your dispatch phone number", body: "Brokers and drivers call and text this number. Your dispatcher answers 24/7 and forwards anything urgent to you.", cta: "Choose number", art: "AGENT", artW: "96px", artR: "50%" },
  { id: "eld", title: "Connect your ELD", body: "Samsara, Motive or Omnitracs. Live location and hours so your dispatcher plans around real availability.", cta: "Connect ELD", optional: true, art: "/assets/truck-white.png", artW: "170px", artR: "0" },
];

export const SIDE_NAV: [string, string, boolean][] = [["Home", I.home, true], ["Trucks", I.truck, false], ["Drivers", I.users, false], ["Loads", I.doc, false], ["Messages", I.chat, false], ["Settings", I.gear, false]];

/** Truck boxes in the loading graphic. */
export const N_BOX = 36;
/** Setup guide tasks done before the agent starts searching. */
export const AGENT_ACTIVE_AFTER = 4;
