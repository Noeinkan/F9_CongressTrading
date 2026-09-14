// Screenshot config for the congressional disclosure dashboard.
//
// Shoots the PUBLIC DEMO, not the private tracker. The landing card links to the
// demo, so its frames must show what a visitor who clicks through will see: the
// frozen snapshot (demo/demo.json → data.snapshot), the demo banner, the nav
// without /executive. Re-shot this way on 2026-09-14.
//
//   node C:/Personal_utilities/screenshot-kit/shotkit.mjs
//
// Notes for the next run:
//  * No server to start: baseUrl is the deployed demo, and `allowHosts` lets the
//    kit's external-request block through to it. To shoot a local demo instead,
//    run demo.json → runLocally plus `cd frontend && npm run dev`, and set
//    baseUrl to http://127.0.0.1:5173 (the session cookie is Secure on the
//    deployed demo only, so a local run needs no change beyond the URL).
//  * `setup` opens /demo once, which mints the demo session and redirects to /.
//    Every shot after it reuses that cookie. Arriving at / without it shows the
//    login form, and every frame would be that form.
//  * Everything in frame is public record — House and Senate periodic
//    transaction reports — so nothing needs masking.
//  * `/executive` is hidden in the demo; the snapshot has no OGE filings.
//  * Rows in the "latest activity" preview can be municipal bonds with no
//    ticker, which screenshot as a column of em-dashes. The trades shot scrolls
//    to a resolved symbol's Trade history instead.

const DEMO_HOST = "congress.demos.noeinsolutions.com";

export default {
  baseUrl: `https://${DEMO_HOST}`,
  allowHosts: [DEMO_HOST],
  viewport: { width: 1440, height: 900 },
  colorScheme: "light",

  async setup(page) {
    await page.goto(`https://${DEMO_HOST}/demo`, { waitUntil: "networkidle", timeout: 90_000 });
    await page.waitForURL((url) => !url.pathname.startsWith("/demo"), { timeout: 60_000 });
  },

  shots: [
    {
      name: "01-overview",
      shows: "The active slice: transactions, members, tickers and disclosed range across House and Senate",
      path: "/",
      waitFor: "table",
      settleMs: 2000,
    },
    {
      name: "02-patterns",
      shows: "Committee relevance: each member's trades scored against the committees they sit on",
      path: "/patterns",
      waitFor: "table",
      settleMs: 2000,
    },
    {
      name: "03-ticker-trades",
      shows: "A single symbol's trade history: who traded it, amount band, price at trade against now, return since",
      path: "/tickers",
      waitFor: "table",
      async prepare(page) {
        const heading = page.getByText("Trade history", { exact: true }).first();
        await heading.waitFor({ state: "visible", timeout: 60_000 });
        await page.waitForTimeout(1500);
        await heading.evaluate((el) => {
          const card = el.closest(".mantine-Paper-root") || el;
          const top = card.getBoundingClientRect().top + window.scrollY - 110;
          window.scrollTo({ top, behavior: "instant" });
        });
        await page.waitForTimeout(800);
      },
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
      path: "/raw",
      waitFor: "table",
      settleMs: 1500,
    },
  ],
};
