import type { RouteObject } from "react-router";
import { RequireOwnedBar, RequireSignIn } from "./guards";
import { ApplicationLayout, ApplicationResume, ApplicationStep } from "../application/ApplicationRoutes";
import { ApplicationDetailPage } from "../owner/ApplicationDetailPage";
import { ApplicationsPage } from "../owner/ApplicationsPage";
import { BarsPage } from "../owner/BarsPage";
import { BarHomePage } from "../bar/BarHomePage";
import { BarInfoPage } from "../bar/BarInfoPage";
import { BarPhotosPage } from "../bar/BarPhotosPage";
import { BarStatusPage } from "../bar/BarStatusPage";
import { MenuItemPage } from "../menu/MenuItemPage";
import { MenuPage } from "../menu/MenuPage";
import { ImportJobPage } from "../menuImport/ImportJobPage";
import { ImportStartPage } from "../menuImport/ImportStartPage";
import { EntryPage, LoginPage, NotFoundPage } from "./pages";

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
      { path: "bars/:barId/info", element: <RequireOwnedBar>{(bar) => <BarInfoPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/photos", element: <RequireOwnedBar>{(bar) => <BarPhotosPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/status", element: <RequireOwnedBar>{(bar) => <BarStatusPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/menu", element: <RequireOwnedBar>{(bar) => <MenuPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/menu/new", element: <RequireOwnedBar>{(bar) => <MenuItemPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/menu/import", element: <RequireOwnedBar>{(bar) => <ImportStartPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/menu/import/:menuImportId", element: <RequireOwnedBar>{(bar) => <ImportJobPage bar={bar} />}</RequireOwnedBar> },
      { path: "bars/:barId/menu/:barMenuItemId", element: <RequireOwnedBar>{(bar) => <MenuItemPage bar={bar} />}</RequireOwnedBar> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
