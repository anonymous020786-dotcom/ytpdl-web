import { useEffect, useRef } from "react";

import { getToken } from "../api/client";
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
      const [token, wsBaseUrl] = await Promise.all([getToken(), getWsBaseUrl()]);
      if (cancelled) return;
      const url = `${wsBaseUrl}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
      ws = new WebSocket(url);
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
