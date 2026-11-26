# Cross-app links: SearchForAlpha ↔ 13F Screener ↔ Congress Trading

The same file is in all three repos. It is the contract for linking between them:
if one app renames a page below, the other two break silently, so change it here
and in both siblings in the same round.

## Rule: owner-only, production only, never a demo

The links connect the owner's production copies of the three apps, each behind
the owner's own email + password login. They are never shown on a public demo
and never point at one: any `*.demos.*` address is refused in code, whatever a
variable says.

| App | Production | Login |
| --- | --- | --- |
| SearchForAlpha (F2) | https://alpha.noeinsolutions.com | `hosted/login.py` |
| 13F Screener (F8) | https://13f.noeinsolutions.com | `src/api/owner_login.py`, on with `F8_LOGIN_REQUIRED=1` |
| Congress Trading (F9) | https://congress.noeinsolutions.com | `src/api/owner_login.py`, on when `SITE_LOGIN_PASSWORD_HASH` is set |

All three read the same pair, so one password opens all three:
`SITE_LOGIN_EMAIL` and `SITE_LOGIN_PASSWORD_HASH` (a Werkzeug `scrypt:`/`pbkdf2:`
hash: the plain password never reaches the server). Each also needs its own
cookie secret of 32+ characters: `SITE_SECRET_KEY` on F2 and F8,
`APP_SESSION_SECRET` on F9. A half-configured login refuses to start.

**Who sees the links:**

| App | Shown to |
| --- | --- |
| F2 | `local` mode (`python main.py`); on the hosted site only the owner's own login (`SITE_LOGIN_EMAIL`), not other admins nor invited users; never in `demo` mode |
| F8 | off the demo, and only when `/api/session` answers: behind the login that means signed in; with the login off it is local development |
| F9 | off the demo, and only when signed in (or with auth off, local development) |

## Who links where

| App | Key | Opens on a ticker at |
| --- | --- | --- |
| SearchForAlpha (F2) | `sfa` | `/ticker/<T>` |
| 13F Screener (F8) | `13f` | `/holdings-search?q=<T>` |
| Congress Trading (F9) | `congress` | `/tickers?ticker=<T>` |

`<T>` is the upper-case symbol, URL-encoded. With no ticker a link goes to `/`.

Every link adds `from=<key of the app that sent it>`, for example
`https://13f.noeinsolutions.com/holdings-search?q=AAPL&from=sfa`. The receiving
app shows "← Back to" plus the sender's name for as long as the visitor stays (the
React apps remember it for the tab's session, since in-app navigation drops the
query string). An unknown `from` value is ignored. Links open in the same tab.
A signed-out visitor lands on the login page first and is sent on to the linked
page afterwards (F2 and F8 keep the full address through the login; F9 keeps it
through its React login route).

## Overriding the addresses

Unset means production. An empty value hides that app.

| App | Variables | Read |
| --- | --- | --- |
| F2 | `SFA_13F_URL`, `SFA_CONGRESS_URL` | at runtime, from the process environment |
| F8 | `VITE_SEARCHFORALPHA_URL`, `VITE_CONGRESS_URL` | at build time, from `frontend/.env` |
| F9 | `VITE_SEARCHFORALPHA_URL`, `VITE_13F_URL` | at build time, from `frontend/.env` |

## Where each app keeps its table

- **F2:** `lib/dash/sibling_apps.py`; header APPS menu and the SUMMARY strip in
  `lib/dash/callbacks/sibling_apps.py`.
- **F8 / F9:** `frontend/src/config/siblingApps.ts` (identical in both, only `SELF`
  differs); visibility and header menu in `frontend/src/components/SiblingApps.tsx`.
