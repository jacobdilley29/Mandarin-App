import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, type Settings } from "./api";
import { applyTheme } from "./theme";

interface SettingsCtx {
  settings: Settings | null;
  error: string | null;
  saving: boolean;
  update: (patch: Partial<Settings>) => Promise<void>;
}

const Ctx = createContext<SettingsCtx>({
  settings: null,
  error: null,
  saving: false,
  update: async () => {},
});

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s);
        applyTheme(s.theme);
        try {
          localStorage.setItem("theme", s.theme);
        } catch {
          /* ignore */
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  const update = useCallback(
    async (patch: Partial<Settings>) => {
      setSettings((prev) => (prev ? { ...prev, ...patch } : prev));
      if (patch.theme) {
        applyTheme(patch.theme);
        try {
          localStorage.setItem("theme", patch.theme);
        } catch {
          /* ignore */
        }
      }
      setSaving(true);
      try {
        const saved = await api.updateSettings(patch);
        setSettings(saved);
        setError(null);
      } catch (e) {
        setError(String(e));
      } finally {
        setSaving(false);
      }
    },
    [],
  );

  return <Ctx.Provider value={{ settings, error, saving, update }}>{children}</Ctx.Provider>;
}

export function useSettings(): SettingsCtx {
  return useContext(Ctx);
}
