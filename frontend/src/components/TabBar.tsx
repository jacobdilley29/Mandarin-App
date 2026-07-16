import { NavLink } from "react-router-dom";

// Bottom tab bar: 學 Learn / 複習 Review / 聽 Listen / 說 Speak / 聊 Talk / 我 Me.
// Han label is the hero; the English gloss sits small beneath.
interface Tab {
  to: string;
  han: string;
  en: string;
}

const TABS: Tab[] = [
  { to: "/learn", han: "學", en: "Learn" },
  { to: "/review", han: "複習", en: "Review" },
  { to: "/listen", han: "聽", en: "Listen" },
  { to: "/speak", han: "說", en: "Speak" },
  { to: "/talk", han: "聊", en: "Talk" },
  { to: "/me", han: "我", en: "Me" },
];

export function TabBar() {
  return (
    <nav
      className="sticky bottom-0 z-20 border-t border-border bg-surface/95 backdrop-blur"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      aria-label="Primary"
    >
      <ul className="mx-auto flex max-w-xl">
        {TABS.map((t) => (
          <li key={t.to} className="flex-1">
            <NavLink
              to={t.to}
              className={({ isActive }) =>
                [
                  "tap flex flex-col items-center justify-center gap-0.5 py-2 text-center transition-colors",
                  isActive ? "text-primary" : "text-ink-faint hover:text-ink-soft",
                ].join(" ")
              }
            >
              <span lang="zh-Hant" className="font-han text-lg leading-none">
                {t.han}
              </span>
              <span className="text-[0.62rem] font-medium tracking-wide">{t.en}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
