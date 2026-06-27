"use client";

// Entry view: Chris's VeriFarm login gate → the GenUI copilot. The copilot
// streams the agent's progress (status frames) and renders each `component`
// frame via the registry.
import { useCallback, useRef, useState } from "react";

import { ComponentRegistry } from "@/components/genui/ComponentRegistry";
import { LoginPage } from "@/components/auth/LoginPage";
import { streamChat, type ComponentFrame } from "@/lib/sse_client";

interface RenderedComponent {
  id: number;
  componentType: string;
  props: Record<string, unknown>;
}

const EXAMPLES = [
  "What is farmer F-1's verified history?",
  "Is farmer F-1 eligible for the input loan?",
  "Show cooperative stats",
];

export default function Page() {
  const [role, setRole] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [components, setComponents] = useState<RenderedComponent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);

  const cancelRef = useRef<null | (() => void)>(null);
  const nextId = useRef(0);

  const ask = useCallback(
    (raw: string) => {
      const q = raw.trim();
      if (!q || streaming) return;

      cancelRef.current?.(); // cancel any in-flight stream
      setComponents([]);
      setError(null);
      setStatus("Starting…");
      setStreaming(true);

      cancelRef.current = streamChat(q, {
        onStatus: (message) => setStatus(message),
        onComponent: (frame: ComponentFrame) =>
          setComponents((prev) => [
            ...prev,
            {
              id: nextId.current++,
              componentType: frame.componentType,
              props: frame.props,
            },
          ]),
        onError: (message) => setError(message),
        onDone: () => {
          setStreaming(false);
          setStatus(null);
        },
      });
    },
    [streaming],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    ask(query);
  };

  if (!role) {
    return <LoginPage onLogin={setRole} />;
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="font-display text-3xl uppercase tracking-wide text-white">
            VeriFarm Copilot
          </h1>
          <p className="mt-1 font-accent text-lg text-white/50">
            Ask about a farmer&apos;s verified history, loan eligibility, or
            cooperative statistics.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setRole(null)}
          className="rounded-md border border-white/15 px-3 py-1.5 text-xs text-white/60 transition hover:border-primary hover:text-primary"
        >
          Log out
        </button>
      </header>

      <form onSubmit={onSubmit} className="mb-4 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask the copilot…"
          className="flex-1 rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          type="submit"
          disabled={streaming || !query.trim()}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:opacity-50"
        >
          {streaming ? "Streaming…" : "Ask"}
        </button>
      </form>

      <div className="mb-8 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => {
              setQuery(ex);
              ask(ex);
            }}
            disabled={streaming}
            className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/60 transition hover:border-primary hover:text-primary disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>

      {status ? (
        <div className="mb-4 flex items-center gap-2 text-sm text-white/60">
          <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
          {status}
        </div>
      ) : null}

      {error ? (
        <div className="mb-4 rounded-md border-l-4 border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="space-y-4">
        {components.map((c) => {
          const Component = ComponentRegistry[c.componentType];
          return (
            <section
              key={c.id}
              className="rounded-lg border border-white/10 bg-white p-4 shadow-sm"
            >
              {Component ? (
                <Component {...c.props} />
              ) : (
                <p className="text-sm text-gray-400">
                  Unsupported component: {c.componentType}
                </p>
              )}
            </section>
          );
        })}
      </div>
    </main>
  );
}
