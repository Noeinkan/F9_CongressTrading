import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "navy",
  colors: {
    navy: [
      "#e8eefc",
      "#c5d4f5",
      "#9fb8ed",
      "#789ce4",
      "#5280db",
      "#2d64d2",
      "#1e3a8a",
      "#182f6e",
      "#122452",
      "#0c1936",
    ],
    parchment: [
      "#f7f2e8",
      "#f2eadf",
      "#ede3d3",
      "#e8dcc7",
      "#e3d5bb",
      "#deceaf",
      "#d9c7a3",
      "#d4c097",
      "#cfb98b",
      "#cab27f",
    ],
  },
  fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  headings: {
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    fontWeight: "600",
  },
  defaultRadius: "md",
});
