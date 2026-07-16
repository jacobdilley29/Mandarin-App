import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type AppStatus } from "./api";

const StatusContext = createContext<AppStatus | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AppStatus | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  return <StatusContext.Provider value={status}>{children}</StatusContext.Provider>;
}

/** Current backend feature-flag status, or null while loading / on error. */
export function useStatus(): AppStatus | null {
  return useContext(StatusContext);
}
