import { createBrowserRouter, Navigate } from "react-router-dom";

import { RequireAuth } from "@/components/RequireAuth";
import { SidebarLayout } from "@/components/SidebarLayout";
import { Access } from "@/routes/Access";
import { AccessEnded } from "@/routes/AccessEnded";
import { AccessVerify } from "@/routes/AccessVerify";
import { DemoEntry } from "@/routes/DemoEntry";
import { Executive } from "@/routes/Executive";
import { Home } from "@/routes/Home";
import { Login } from "@/routes/Login";
import { Members } from "@/routes/Members";
import { NotFound } from "@/routes/NotFound";
import { Patterns } from "@/routes/Patterns";
import { Raw } from "@/routes/Raw";
import { Review } from "@/routes/Review";
import { Senate } from "@/routes/Senate";
import { Tickers } from "@/routes/Tickers";

export const router = createBrowserRouter(
  [

  {
    path: "/login",
    element: <Login />,
  },
  {
    // The demo's own sign-in flow: outside RequireAuth, since a signed-out
    // visitor must be able to reach it.
    path: "/access",
    element: <Access />,
  },
  {
    path: "/access/verify",
    element: <AccessVerify />,
  },
  {
    path: "/access/ended",
    element: <AccessEnded />,
  },
  {
    // The URL on the landing page; routes into whichever of the above (or
    // straight into the dashboard) matches the visitor's current access.
    // Falls back to /login when this deployment has no demo at all.
    path: "/demo",
    element: <DemoEntry />,
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <SidebarLayout />,
        children: [
          { index: true, element: <Home /> },
          { path: "senate", element: <Senate /> },
          { path: "executive", element: <Executive /> },
          { path: "raw", element: <Raw /> },
          { path: "review", element: <Review /> },
          { path: "patterns", element: <Patterns /> },
          { path: "members", element: <Members /> },
          { path: "tickers", element: <Tickers /> },
        ],
      },
    ],
  },
  { path: "/404", element: <NotFound /> },
  { path: "*", element: <Navigate to="/404" replace /> },
  ],
  {
    future: {
      v7_relativeSplatPath: true,
    },
  },
);
