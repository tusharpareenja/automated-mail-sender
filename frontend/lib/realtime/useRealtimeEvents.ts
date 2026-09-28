"use client";

import { useEffect, useRef } from "react";
import {
  useRealtimeContext,
  type RealtimeEvent,
} from "@/lib/realtime/RealtimeProvider";

export type { RealtimeEvent };

export function useRealtimeEvents(onEvent: (event: RealtimeEvent) => void) {
  const { status, subscribe } = useRealtimeContext();
  const handler = useRef(onEvent);

  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => subscribe((event) => handler.current(event)), [subscribe]);

  return status;
}
