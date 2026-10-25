// Injected into the prebuilt demo app before capture.
// The prebuilt dist predates two copy changes now in manceps-app/src:
// the agent introduces itself as an AI on every call, and booking/signing are
// locked to owner approval. This rewrites the old demo copy to match, and
// names the agent "Manceps" (the firm's chosen persona) for marketing.
(() => {
  const RULES = [
    [/^Hey (\w+), Arjun here\. /, "Hi $1, it's Manceps, the AI dispatcher. "],
    [/^Hi Daniel, sorry to bug you on your reset\.$/, "Hi Daniel, it's Manceps, the AI dispatcher. Sorry to bug you on your reset."],
    [/Jordan's approving it\./, "It's waiting on your dispatcher's yes."],
    [/Rate con and dock info are coming to your WhatsApp\./, "Rate con and dock info come to your WhatsApp once it's approved."],
    [/\$780\. Want it\?/, "$780. Want me to send it to your dispatcher for a yes?"],
    [/^Yeah, book it\.$/, "Yeah, send it."],
    [/Books and signs within your limit/, "Runs the rest; booking and signing still wait for you"],
    [/Routine work on his own/, "Routine work on its own"],
    [/Arjun suggests, you decide everything/, "Suggests everything, you decide"],
    [/What Arjun can do on his own/, "What Manceps can do on its own"],
    [/Arjun logs everything he does\./, "Manceps logs everything it does."],
    [/Arjun's notes/, "Agent notes"],
    [/Arjun's permissions/, "Permissions"],
    [/Arjun/g, "Manceps"],
  ];
  const fix = (s) => RULES.reduce((acc, [re, to]) => acc.replace(re, to), s);
  const walk = (root) => {
    const it = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = it.nextNode(); n; n = it.nextNode()) {
      const v = n.nodeValue;
      if (v && /Arjun|Jordan|Want it\?|book it\.|signs within|his own|he does|bug you/.test(v)) {
        const f = fix(v);
        if (f !== v) n.nodeValue = f;
      }
    }
    if (root.querySelectorAll) {
      root.querySelectorAll("[placeholder],[aria-label]").forEach((el) => {
        for (const a of ["placeholder", "aria-label"]) {
          const v = el.getAttribute(a);
          if (v && v.includes("Arjun")) el.setAttribute(a, fix(v));
        }
      });
    }
  };
  const start = () => {
    walk(document.body);
    new MutationObserver((ms) => {
      for (const m of ms) {
        if (m.type === "characterData") walk(m.target.parentNode || document.body);
        m.addedNodes.forEach((n) => walk(n.nodeType === 3 ? n.parentNode || document.body : n));
        if (m.type === "attributes") walk(m.target);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["placeholder", "aria-label"] });
  };
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
