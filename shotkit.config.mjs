// Screenshot config for the congressional disclosure dashboard.
//
// Notes for the next run:
//  * `npm start` boots BOTH the FastAPI backend (:9001, from `.venv`) and Vite
//    (:5173). readyPath must be the Vite port.
//  * Everything in frame is public record — House and Senate periodic
//    transaction reports — read out of the local SQLite build. No key, no
//    credential and no private data is involved, so nothing needs masking.
//  * `/executive` renders an empty state on this data build; do not add a shot
//    for it without checking the page again first.
//  * Rows in the "latest activity" preview are municipal bonds with no ticker,
//    which screenshot as a column of em-dashes. Shots that want the table
//    filled scroll past the preview into the resolved-symbol views instead.

export default {
  server: {
    command: "npm start",
    readyPath: "http://127.0.0.1:5173/",
    readyTimeoutMs: 120_000,
  },
  baseUrl: "http://127.0.0.1:5173",
  viewport: { width: 1440, height: 900 },
  colorScheme: "light",

  shots: [
    {
      name: "01-overview",
      shows: "The active slice: transactions, members, tickers and disclosed range across House and Senate",
      path: "/",
      waitFor: "table",
      settleMs: 1200,
    },
    {
      name: "02-patterns",
      shows: "Committee relevance: each member's trades scored against the committees they sit on",
      path: "/patterns",
      waitFor: "table",
      settleMs: 1200,
    },
    {
      name: "03-ticker-profile",
      shows: "A single symbol: who traded it, buy/sell split, disclosed range and return since trade",
      path: "/tickers",
      waitFor: "table",
      settleMs: 1200,
    },
    {
      name: "04-ticker-chart",
      shows: "The price overlay under a ticker's disclosure timeline",
      path: "/tickers",
      waitFor: "table",
      async prepare(page) {
        await page.waitForTimeout(1500);
        await page.mouse.wheel(0, 900);
        await page.waitForTimeout(1200);
      },
      settleMs: 1000,
    },
    {
      name: "05-raw-data",
      shows: "The normalised transaction table the pipeline exports, straight out of SQLite",
      path: "/raw-data",
      waitFor: "table",
      settleMs: 1500,
    },
  ],
};
