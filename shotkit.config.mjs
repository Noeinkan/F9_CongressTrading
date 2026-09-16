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
//    SHOTKIT_BASE_URL=http://127.0.0.1:5173.
//  * The demo is behind an email gate, and there is no back door for the kit.
//    Sign in once in a normal browser (the code arrives by email; on a local run
//    with DEMO_MAIL_BACKEND=console it is printed in the API log), copy the value
//    of the `f9_demo_access` cookie from the browser's dev tools, and run:
//      F9_DEMO_ACCESS_COOKIE=<value> node C:/Personal_utilities/screenshot-kit/shotkit.mjs
//    `setup` hands that cookie to the kit's browser. It is a real session, so it
//    has the same 45 minutes as anyone else's; the banner in frame shows the clock.
//  * Everything in frame is public record — House and Senate periodic
//    transaction reports — so nothing needs masking.
//  * `/executive` is hidden in the demo; the snapshot has no OGE filings.
//  * Rows in the "latest activity" preview can be municipal bonds with no
//    ticker, which screenshot as a column of em-dashes. The trades shot scrolls
//    to a resolved symbol's Trade history instead.

const DEMO_HOST = "congress.demos.noeinsolutions.com";
const BASE_URL = process.env.SHOTKIT_BASE_URL || `https://${DEMO_HOST}`;

export default {
  baseUrl: BASE_URL,
  allowHosts: [DEMO_HOST],
  viewport: { width: 1440, height: 900 },
  colorScheme: "light",

  async setup(page) {
    const token = process.env.F9_DEMO_ACCESS_COOKIE;
    if (!token) {
      throw new Error(
        "F9_DEMO_ACCESS_COOKIE is not set: sign in to the demo in a browser and pass the " +
          "f9_demo_access cookie value (see the notes at the top of shotkit.config.mjs).",
      );
    }
    const url = new URL(BASE_URL);
    await page.context().addCookies([
      {
        name: "f9_demo_access",
        value: token,
        domain: url.hostname,
        path: "/",
        httpOnly: true,
        secure: url.protocol === "https:",
        sameSite: "Lax",
      },
    ]);
    await page.goto(`${BASE_URL}/demo`, { waitUntil: "networkidle", timeout: 90_000 });
    await page.waitForURL((u) => !u.pathname.startsWith("/demo") && !u.pathname.startsWith("/access"), {
      timeout: 60_000,
    });
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
