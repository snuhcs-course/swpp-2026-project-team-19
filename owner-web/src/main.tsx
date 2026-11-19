import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { createSupabaseGateway } from "./auth/supabaseGateway";
import { readConfig } from "./config";
import { createQueryClient } from "./queryClient";
import "./styles/tokens.css";
import "./styles/global.css";

const root = document.getElementById("root");
if (!root) throw new Error("The page has no #root element.");

const gateway = createSupabaseGateway(readConfig());
const queryClient = createQueryClient();

createRoot(root).render(
  <StrictMode>
    <App gateway={gateway} queryClient={queryClient} />
  </StrictMode>,
);
