import type { RouteObject } from "react-router";
import { RequireOwnedBar, RequireSignIn } from "./guards";
import { ApplicationLayout, ApplicationResume, ApplicationStep } from "../application/ApplicationRoutes";
import { ApplicationDetailPage } from "../owner/ApplicationDetailPage";
import { ApplicationsPage } from "../owner/ApplicationsPage";
import { BarsPage } from "../owner/BarsPage";
import { BarHomePage, EntryPage, LoginPage, NotFoundPage } from "./pages";

/** The app is served at /owner/ (backend/app/owner_web); every path here is inside that basename. */
export const OWNER_BASENAME = "/owner";

export const ownerRoutes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireSignIn />,
    children: [
      { index: true, element: <EntryPage /> },
      {
        path: "apply",
        element: <ApplicationLayout />,
        children: [
          { index: true, element: <ApplicationResume /> },
          { path: ":step", element: <ApplicationStep /> },
        ],
      },
      { path: "applications", element: <ApplicationsPage /> },
      { path: "applications/:applicationId", element: <ApplicationDetailPage /> },
      { path: "bars", element: <BarsPage /> },
      { path: "bars/:barId", element: <RequireOwnedBar>{(bar) => <BarHomePage bar={bar} />}</RequireOwnedBar> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
