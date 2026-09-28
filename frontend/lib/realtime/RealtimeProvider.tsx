"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { authApi } from "@/lib/api/auth";
import { env } from "@/lib/config/env";

export type RealtimeEvent = {
  type: string;
  campaign_id?: string;
  email_id?: string;
  lead_id?: string;
  destination_url?: string;
  recipient_email?: string;
  link_clicks?: number;
  classification?: string;
  confidence?: number;
  reasons?: string[];
  is_first_unique_open?: boolean;
  filename?: string;
  kind?: string;
  asset_id?: string;
  download?: boolean;
  source?: string;
  status?: string;
};

type Listener = (event: RealtimeEvent) => void;

type RealtimeContextValue = {
  status: "idle" | "connecting" | "live" | "offline";
  subscribe: (listener: Listener) => () => void;
};

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export function RealtimeProvider({
  enabled,
  children,
}: {
  enabled: boolean;
  children: ReactNode;
}) {
  const listeners = useRef(new Set<Listener>());
  const [status, setStatus] = useState<RealtimeContextValue["status"]>("idle");

  const subscribe = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      return;
    }

    let closed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let attempts = 0;

    function emit(event: RealtimeEvent) {
      for (const listener of listeners.current) {
        try {
          listener(event);
        } catch {
          // Keep one bad subscriber from killing the socket fan-out.
        }
      }
    }

    async function connect() {
      if (closed) return;
      setStatus(attempts === 0 ? "connecting" : "offline");
      try {
        const { token } = await authApi.wsTicket();
        if (closed) return;
        socket = new WebSocket(`${env.wsUrl}?token=${encodeURIComponent(token)}`);
        socket.onmessage = (message) => {
          try {
            const body = JSON.parse(message.data) as { data?: RealtimeEvent[] };
            for (const event of body.data ?? []) {
              if (event.type === "PING") continue;
              if (event.type === "CONNECTED") setStatus("live");
              else setStatus("live");
              emit(event);
            }
          } catch {
            return;
          }
        };
        socket.onopen = () => {
          attempts = 0;
          setStatus("live");
        };
        socket.onclose = () => {
          if (closed) return;
          setStatus("offline");
          attempts += 1;
          const delay = Math.min(15000, 1000 * 2 ** attempts);
          reconnectTimer = window.setTimeout(() => {
            void connect();
          }, delay);
        };
      } catch {
        if (closed) return;
        setStatus("offline");
        reconnectTimer = window.setTimeout(() => {
          void connect();
        }, 5000);
      }
    }

    void connect();
    return () => {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [enabled]);

  const value = useMemo(() => ({ status, subscribe }), [status, subscribe]);

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtimeContext() {
  const value = useContext(RealtimeContext);
  if (!value) {
    throw new Error("useRealtimeContext must be used inside RealtimeProvider");
  }
  return value;
}
