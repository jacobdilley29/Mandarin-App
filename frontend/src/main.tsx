import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { applyTheme, type ThemePref } from "./theme";
import "./index.css";

// Apply any saved theme preference before first paint to avoid a flash.
try {
  const saved = localStorage.getItem("theme") as ThemePref | null;
  if (saved) applyTheme(saved);
} catch {
  /* localStorage unavailable — fall back to system preference */
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
