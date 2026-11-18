import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import type { AuthGateway } from "./auth/gateway";
import { SessionProvider } from "./auth/SessionProvider";
import { OWNER_BASENAME, ownerRoutes } from "./routes/routes";

/** The owner web: server data (TanStack Query), the owner's session, and the screens (React Router). */
export default function App({ gateway, queryClient }: { gateway: AuthGateway; queryClient: QueryClient }) {
  const [router] = useState(() => createBrowserRouter(ownerRoutes, { basename: OWNER_BASENAME }));
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider gateway={gateway}>
        <RouterProvider router={router} />
      </SessionProvider>
    </QueryClientProvider>
  );
}
