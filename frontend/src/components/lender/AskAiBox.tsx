"use client";

// "Ask AI about this farmer" -- a simple direct LLM call, no ReAct loop, no
// tool calls, no SSE. Calls our own backend proxy (POST /api/v1/ai/ask-about-
// farmer) instead of the LLM provider directly -- the Featherless API key
// lives only in the backend's .env now, never in the client bundle. The full
// farmer profile JSON still travels with every request and conversation
// history is still kept in React state so follow-ups work; only the
// credential boundary moved.
import { useState } from "react";
import { ChevronDown, MessageCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

export function AskAiBox({ farmerProfile }: { farmerProfile: unknown }) {
  const [expanded, setExpanded] = useState(false);
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    const question = input.trim();
    if (!question || loading) return;

    const nextHistory: ChatMessage[] = [...history, { role: "user", content: question }];
    setHistory(nextHistory);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/ask-about-farmer`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          farmer_profile: farmerProfile,
          messages: nextHistory,
        }),
      });

      if (!response.ok) {
        throw new Error(`${response.status}: ${await response.text()}`);
      }

      const data = await response.json();
      setHistory([...nextHistory, { role: "assistant", content: data.content ?? "(no response)" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-6 border-t border-white/10 pt-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 text-sm font-medium text-white/70 hover:text-primary"
      >
        <MessageCircle className="h-4 w-4" />
        Ask AI about this farmer
        <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded ? (
        <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 backdrop-blur">
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {history.length === 0 ? (
              <p className="text-xs text-white/40">
                Ask a question about this farmer&apos;s verified profile, e.g. &ldquo;is this
                farmer creditworthy?&rdquo;
              </p>
            ) : null}
            {history.map((m, i) => (
              <div
                key={i}
                className={`rounded-md p-2 text-sm ${
                  m.role === "user" ? "bg-white/5 text-white/80" : "bg-primary/10 text-primary"
                }`}
              >
                <span className="font-medium">{m.role === "user" ? "You: " : "AI: "}</span>
                {m.content}
              </div>
            ))}
            {loading ? <p className="text-xs text-white/40">Thinking…</p> : null}
          </div>

          {error ? <p className="mt-2 text-xs text-destructive">{error}</p> : null}

          <div className="mt-3 flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") ask();
              }}
              placeholder="Ask a question…"
              className="flex-1 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none"
            />
            <button
              type="button"
              onClick={ask}
              disabled={loading || !input.trim()}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default AskAiBox;
