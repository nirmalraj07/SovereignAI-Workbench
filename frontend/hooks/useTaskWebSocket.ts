"use client";
import { useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api-client";
import { useAuthStore } from "@/lib/store";
import type { TaskStatusResponse } from "@/types";

/**
 * Subscribes to /api/tasks/ws/{taskId} and streams live agent-run progress.
 * Falls back gracefully — if the socket errors, the caller can still poll
 * api.tasks.status(taskId) since the REST endpoint covers the same state.
 *
 * The JWT travels as a `token` query parameter, not an Authorization
 * header — the browser's native WebSocket API cannot set custom headers,
 * so this is the standard pattern for authenticating a browser-originated
 * WebSocket. The backend also enforces that the token's owner matches the
 * task's submitter (or is an admin) — this endpoint previously had no
 * authentication at all.
 */
export function useTaskWebSocket(taskId: string | null) {
  const [status, setStatus] = useState<TaskStatusResponse | null>(null);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (!taskId || !token) return;
    const socket = new WebSocket(wsUrl(`/api/tasks/ws/${taskId}?token=${encodeURIComponent(token)}`));
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as TaskStatusResponse;
        setStatus(data);
      } catch {
        // ignore malformed frames
      }
    };

    return () => socket.close();
  }, [taskId, token]);

  return { status, connected };
}
