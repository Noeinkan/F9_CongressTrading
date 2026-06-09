import { createBrowserRouter, Navigate } from "react-router-dom";

import { RequireAuth } from "@/components/RequireAuth";
import { SidebarLayout } from "@/components/SidebarLayout";
import { Home } from "@/routes/Home";
import { Login } from "@/routes/Login";
import { Members } from "@/routes/Members";
import { NotFound } from "@/routes/NotFound";
import { Patterns } from "@/routes/Patterns";
import { Raw } from "@/routes/Raw";
import { Review } from "@/routes/Review";
import { Tickers } from "@/routes/Tickers";

export const router = createBrowserRouter(
  [

  {
    path: "/login",
    element: <Login />,
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <SidebarLayout />,
        children: [
          { index: true, element: <Home /> },
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
