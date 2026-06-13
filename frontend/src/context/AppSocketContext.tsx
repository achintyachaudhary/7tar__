import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

type MessageHandler = (msg: Record<string, unknown>) => void;

interface AppSocketContextValue {
  connected: boolean;
  sendMessage: (channel: string, payload?: Record<string, unknown>) => void;
  subscribe: (channel: string, handler: MessageHandler) => () => void;
}

const AppSocketContext = createContext<AppSocketContextValue | null>(null);

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/app`;
}

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

export function AppSocketProvider({ children }: { children: ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const subsRef = useRef<Map<string, Set<MessageHandler>>>(new Map());
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    const socket = new WebSocket(getWsUrl());
    wsRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      reconnectAttempt.current = 0;
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as Record<string, unknown>;
        const channel = msg.channel as string | undefined;
        if (!channel) return;

        const handlers = subsRef.current.get(channel);
        if (handlers) {
          handlers.forEach((h) => {
            try { h(msg); } catch { /* handler error */ }
          });
        }

        // Also dispatch to wildcard subscribers
        const wildcard = subsRef.current.get("*");
        if (wildcard) {
          wildcard.forEach((h) => {
            try { h(msg); } catch { /* handler error */ }
          });
        }
      } catch {
        // ignore non-JSON
      }
    };

    socket.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Exponential backoff reconnect
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** reconnectAttempt.current,
        RECONNECT_MAX_MS,
      );
      reconnectAttempt.current++;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    socket.onerror = () => {
      socket.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const sendMessage = useCallback(
    (channel: string, payload: Record<string, unknown> = {}) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ channel, ...payload }));
      }
    },
    [],
  );

  const subscribe = useCallback(
    (channel: string, handler: MessageHandler): (() => void) => {
      if (!subsRef.current.has(channel)) {
        subsRef.current.set(channel, new Set());
      }
      subsRef.current.get(channel)!.add(handler);

      return () => {
        const set = subsRef.current.get(channel);
        if (set) {
          set.delete(handler);
          if (set.size === 0) subsRef.current.delete(channel);
        }
      };
    },
    [],
  );

  return (
    <AppSocketContext.Provider value={{ connected, sendMessage, subscribe }}>
      {children}
    </AppSocketContext.Provider>
  );
}

export function useAppSocket(): AppSocketContextValue {
  const ctx = useContext(AppSocketContext);
  if (!ctx) {
    throw new Error("useAppSocket must be used within AppSocketProvider");
  }
  return ctx;
}
