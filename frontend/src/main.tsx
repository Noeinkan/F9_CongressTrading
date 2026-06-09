import "@mantine/core/styles.css";
import "./styles/globals.css";

import { MantineProvider } from "@mantine/core";
import { QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./App";
import { queryClient } from "./api/queryClient";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { FilterProvider } from "./components/FilterContext";
import { theme } from "./theme";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <MantineProvider theme={theme}>
        <FilterProvider>
          <QueryClientProvider client={queryClient}>
            <RouterProvider router={router} future={{ v7_startTransition: true }} />
          </QueryClientProvider>
        </FilterProvider>
      </MantineProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
