import { useEffect, useRef } from "react";

import { getWsBaseUrl } from "../config";

export interface JobEvent {
  job_id: string;
  type?: string;
  state?: string;
  percent?: string | number;
  status?: string;
  speed?: string;
  eta?: string;
  done?: string | number;
  total?: string | number;
  error?: string;
}

/** Same /ws endpoint the web frontend uses — one shared connection, fed to a
 * callback so screens can merge events into whatever local state they hold. */
export function useJobEvents(onEvent: (event: JobEvent) => void, enabled: boolean) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let cancelled = false;

    (async () => {
      const wsBaseUrl = await getWsBaseUrl();
      if (cancelled) return;
      ws = new WebSocket(`${wsBaseUrl}/ws`);
      ws.onmessage = (ev) => {
        try {
          onEventRef.current(JSON.parse(ev.data));
        } catch {
          // ignore malformed frames
        }
      };
    })();

    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [enabled]);
}
