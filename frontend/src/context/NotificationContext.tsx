import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAppSocket } from "./AppSocketContext";

interface NotificationContextValue {
  badges: Record<string, number>;
  clearBadge: (scanType: string) => void;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { subscribe } = useAppSocket();
  const [badges, setBadges] = useState<Record<string, number>>({});

  useEffect(() => {
    const unsub = subscribe("notification", (msg) => {
      const scanType = msg.scan_type as string;
      const count = (msg.count as number) || 0;
      if (scanType && count > 0) {
        setBadges((prev) => ({ ...prev, [scanType]: count }));
      }
    });
    return unsub;
  }, [subscribe]);

  const clearBadge = useCallback((scanType: string) => {
    setBadges((prev) => {
      const next = { ...prev };
      delete next[scanType];
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ badges, clearBadge }),
    [badges, clearBadge],
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    throw new Error("useNotifications must be used within NotificationProvider");
  }
  return ctx;
}
