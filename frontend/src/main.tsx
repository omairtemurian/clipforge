import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import {
  applyTheme,
  readTheme,
  resolveTheme,
  systemPrefersDark,
} from "./lib/theme";

applyTheme(resolveTheme(readTheme(), systemPrefersDark()));

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Missing root element");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
