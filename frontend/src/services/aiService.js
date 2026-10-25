import { useStore } from "../store/useStore";

// Scripted, deterministic AI. The engine tick writes the reply after a short "thinking" delay.
export const aiService = {
  ask: (text) => {
    const q = text.trim();
    if (!q) return;
    const s = useStore.getState();
    const msgs = s.chat.messages;
    if (msgs.length && msgs[msgs.length - 1].role === "user") return; // one pending question at a time
    s.mutate((st) => {
      st.data.seq += 1;
      st.chat.messages.push({ id: `MSG-U-${st.data.seq}`, role: "user", text: q, ts: Date.now(), at: st.clockMin });
    });
    s.openPanel("chat");
  },
  isThinking: (chat) => {
    const last = chat.messages[chat.messages.length - 1];
    return !!last && last.role === "user";
  },
};
