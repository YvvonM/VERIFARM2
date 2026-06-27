// Consumes the backend agent SSE stream (GET /api/chat) and dispatches frames.
//
// Wire contract (one JSON object per `data:` frame):
//   {"type":"status","message":"…"}
//   {"type":"component","componentType":"BarChart","props":{…}}
//   {"type":"error","message":"…"}
// terminated by an `event: end` frame with body `[DONE]`.

export type StatusFrame = { type: "status"; message: string };
export type ComponentFrame = { type: "component"; componentType: string; props: Record<string, unknown> };
export type ErrorFrame = { type: "error"; message: string };
export type Frame = StatusFrame | ComponentFrame | ErrorFrame;

export interface StreamHandlers {
  onStatus?: (message: string) => void;
  onComponent?: (frame: ComponentFrame) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
// When the backend API-key gate is enabled, EventSource can't send the
// X-API-Key header, so the key travels in the URL (?api_key=). Optional.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

/** Open the chat SSE stream for `query`. Returns a cancel function. */
export function streamChat(query: string, handlers: StreamHandlers): () => void {
  let url = `${API_BASE}/api/chat?query=${encodeURIComponent(query)}`;
  if (API_KEY) url += `&api_key=${encodeURIComponent(API_KEY)}`;
  const es = new EventSource(url);

  const close = () => {
    es.close();
    handlers.onDone?.();
  };

  es.onmessage = (event: MessageEvent) => {
    let frame: Frame;
    try {
      frame = JSON.parse(event.data);
    } catch {
      return; // ignore non-JSON keep-alives
    }
    if (frame.type === "status") handlers.onStatus?.(frame.message);
    else if (frame.type === "component") handlers.onComponent?.(frame);
    else if (frame.type === "error") handlers.onError?.(frame.message);
  };

  // Terminal sentinel from the server (`event: end`).
  es.addEventListener("end", close);
  // The server closing the connection surfaces as an error in EventSource;
  // close so the browser doesn't auto-reconnect and replay the query.
  es.onerror = close;

  return () => es.close();
}
