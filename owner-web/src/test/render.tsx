import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { onTestFinished } from "vitest";
import { RouterProvider } from "react-router/dom";
import { SessionProvider } from "../auth/SessionProvider";
import { OWNER_BASENAME, ownerRoutes } from "../routes/routes";
import { FakeGateway } from "./fakeGateway";

/** Renders the whole owner web at `path` (inside /owner), with a fake sign-in and the MSW server as the API. */
export function renderOwnerWeb(path = "/", { gateway = new FakeGateway() }: { gateway?: FakeGateway } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  // Abort requests still in flight, so none of them reaches the next test's API handlers.
  onTestFinished(async () => {
    await queryClient.cancelQueries();
    queryClient.clear();
  });
  const router = createMemoryRouter(ownerRoutes, {
    basename: OWNER_BASENAME,
    initialEntries: [OWNER_BASENAME + path],
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider gateway={gateway}>
        <RouterProvider router={router} />
      </SessionProvider>
    </QueryClientProvider>,
  );
  return { ...view, router, queryClient, gateway };
}
