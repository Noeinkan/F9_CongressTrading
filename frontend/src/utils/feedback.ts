import { version as reactVersion } from "react";

/**
 * Feedback note plumbing — kept out of the component so the compose, validate
 * and delivery rules can be exercised without rendering a modal.
 *
 * Two delivery paths, chosen at runtime by whether `VITE_FEEDBACK_RELAY_URL`
 * is set:
 *
 * - **Relay** — a hosted form endpoint (Web3Forms, Formspree). It answers with
 *   an HTTP status, so a 2xx is the only thing that earns the word "sent".
 * - **mailto** (the default) — hands the composed note to whatever mail client
 *   the visitor has. Nothing can confirm what happens next, so the UI says
 *   "your mail app should be opening", never "sent".
 *
 * Either way the caller shows the composed text back for copying: a note must
 * never be able to vanish silently, because silence here looks exactly like
 * nobody having anything to say.
 *
 * Why not SMTP from our own API: `src/api/` is self-hostable, so any mail
 * credential we shipped would sit in every public clone of the repo.
 */

/** Shown in the subject line and the body footer. ASCII only. */
const APP_NAME = "Congress Trading";

/**
 * Where notes go when `VITE_FEEDBACK_EMAIL` is unset. The studio address, not
 * a personal mailbox: this string ships in the browser bundle where address
 * scrapers can read it.
 */
const FEEDBACK_DEFAULT_EMAIL = "andrea.aita@noeinsolutions.com";

/** Shortest note we accept. Below this there is nothing to act on. */
export const MIN_MESSAGE_LENGTH = 15;

/**
 * Longest note we accept. The textarea's `maxLength` uses this same constant —
 * a hard stop at one number while the validator complains at another is a
 * silent wall to type into.
 */
export const MAX_MESSAGE_LENGTH = 4000;

/** Past this, some mail clients truncate a `mailto:` body without saying so. */
const MAILTO_SAFE_LENGTH = 1800;

export type FeedbackCategoryId = "bug" | "data" | "idea" | "confusing" | "general";

export type FeedbackCategory = {
  id: FeedbackCategoryId;
  /** Accordion heading — emoji is decorative, kept out of the subject line. */
  emoji: string;
  label: string;
  /** ASCII subject fragment: `[Congress Trading] Bug report`. */
  subject: string;
  /** What a note of this kind needs to contain to be actionable. */
  hint: string;
  /**
   * Seeded into the message box as a template rather than a hint — people fill
   * in a shape far more readily than they compose from an empty field.
   */
  placeholder: string;
};

/**
 * In triage order: the ones that need a fix first come first.
 *
 * Typed as a non-empty tuple rather than a plain array: `noUncheckedIndexedAccess`
 * makes `list[0]` possibly-undefined on an array, and the first entry is the
 * fallback the whole module leans on.
 */
export const FEEDBACK_CATEGORIES: readonly [FeedbackCategory, ...FeedbackCategory[]] = [
  {
    id: "bug",
    emoji: "🐞",
    label: "Something is broken",
    subject: "Bug report",
    hint: "A page that errors, a button that does nothing, a chart that never loads. The three lines below are all I need.",
    placeholder: "What I did:\nWhat I expected:\nWhat happened instead:",
  },
  {
    id: "data",
    emoji: "📉",
    label: "The numbers look wrong",
    subject: "Data quality",
    hint: "A figure that disagrees with the filing, a missing trade, a ticker matched to the wrong company. Name the page, filer or ticker so I can find the same row.",
    placeholder:
      "Which number looks wrong:\nWhere I saw it (page, filer, ticker):\nWhat I would expect instead, and why:",
  },
  {
    id: "idea",
    emoji: "💡",
    label: "I have an idea",
    subject: "Feature request",
    hint: "A view, a filter, an export you keep reaching for. What you are trying to achieve matters more than the feature you imagine.",
    placeholder: "What I am trying to do:\nWhat would help:\nHow often I would use it:",
  },
  {
    id: "confusing",
    emoji: "🧭",
    label: "Something confused me",
    subject: "Usability",
    hint: "A label that reads two ways, a number with no unit, a screen you could not find your way back from. This is the kind of problem that is invisible from my side.",
    placeholder:
      "Where I was:\nWhat I was trying to work out:\nWhat I expected the screen to tell me:",
  },
  {
    id: "general",
    emoji: "💬",
    label: "General impressions",
    subject: "General feedback",
    hint: "Anything that does not fit the boxes above — including the blunt version.",
    placeholder: "What works well:\nWhat does not:\nAnything else:",
  },
] as const;

export const DEFAULT_CATEGORY = FEEDBACK_CATEGORIES[0];

export function categoryById(id: FeedbackCategoryId): FeedbackCategory {
  return FEEDBACK_CATEGORIES.find((c) => c.id === id) ?? DEFAULT_CATEGORY;
}

/** Destination inbox. Override with `VITE_FEEDBACK_EMAIL` at build time. */
export function feedbackEmail(): string {
  return (import.meta.env.VITE_FEEDBACK_EMAIL ?? FEEDBACK_DEFAULT_EMAIL).trim();
}

/**
 * Relay endpoint, when one is configured. Empty string means "use mailto",
 * which is what a fresh clone does — no account, no key, no setup.
 */
export function feedbackRelayUrl(): string {
  return (import.meta.env.VITE_FEEDBACK_RELAY_URL ?? "").trim();
}

/** Public form key some relays require (Web3Forms calls it `access_key`). */
function feedbackRelayKey(): string {
  return (import.meta.env.VITE_FEEDBACK_RELAY_KEY ?? "").trim();
}

function appVersion(): string {
  return typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "unknown";
}

/** One row of the context panel: what the visitor reads is what gets sent. */
export type ContextRow = { label: string; value: string };

/**
 * Boring facts only, and every one of them is displayed in the modal before it
 * is sent. Deliberately absent: any account name, hostname, file path, token,
 * cookie or local-storage value. `FeedbackButton.test.tsx` asserts that.
 */
export function collectContext(route: string): ContextRow[] {
  const rows: ContextRow[] = [
    { label: "Page", value: route.trim() || "/" },
    { label: "App version", value: appVersion() },
    { label: "React", value: reactVersion },
  ];
  if (typeof navigator !== "undefined" && navigator.userAgent) {
    rows.push({ label: "Browser / OS", value: navigator.userAgent });
  }
  if (typeof window !== "undefined" && window.innerWidth) {
    rows.push({ label: "Viewport", value: `${window.innerWidth}x${window.innerHeight}` });
  }
  return rows;
}

export type FeedbackNote = {
  category: FeedbackCategory;
  message: string;
  /** Empty when the visitor chose to stay anonymous. */
  replyTo: string;
  /** `null` when the context checkbox was cleared. */
  context: ContextRow[] | null;
  sentAt: Date;
};

/**
 * Why a note cannot be sent, phrased as something to do about it — a button
 * that silently refuses is indistinguishable from a broken one. `null` = valid.
 */
export function validateNote(input: { message: string; replyTo: string }): string | null {
  const message = input.message.trim();
  if (!message) {
    return "Write a line or two first — the message box is empty.";
  }
  if (message.length < MIN_MESSAGE_LENGTH) {
    return `A few more words, please: ${MIN_MESSAGE_LENGTH} characters at least, so there is something to act on.`;
  }
  if (message.length > MAX_MESSAGE_LENGTH) {
    return `That is longer than ${MAX_MESSAGE_LENGTH} characters — trim it, or email the rest.`;
  }
  const replyTo = input.replyTo.trim();
  if (replyTo && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(replyTo)) {
    return "That reply address does not look like an email. Correct it, or clear the field to stay anonymous.";
  }
  return null;
}

/** `[Congress Trading] Bug report` — ASCII, because emoji survives URL encoding but not every mail client. */
export function composeSubject(note: FeedbackNote): string {
  return `[${APP_NAME}] ${note.category.subject}`;
}

function stamp(now: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  let zone = "local time";
  try {
    zone = Intl.DateTimeFormat().resolvedOptions().timeZone || zone;
  } catch {
    /* Intl is always present in supported browsers; never fail composing over it. */
  }
  return `${date} ${time} (${zone})`;
}

/** Fixed sections in a fixed order, so a full inbox stays skimmable. */
export function composeBody(note: FeedbackNote): string {
  const lines = [
    `Type:  ${note.category.label}`,
    `Sent:  ${stamp(note.sentAt)}`,
    `Reply: ${note.replyTo.trim() || "not given (anonymous)"}`,
    "",
    "--- Message ---",
    note.message.trim(),
  ];
  if (note.context && note.context.length > 0) {
    const width = Math.max(...note.context.map((row) => row.label.length));
    lines.push(
      "",
      "--- Context ---",
      ...note.context.map((row) => `${row.label.padEnd(width)}  ${row.value}`),
    );
  }
  lines.push("", `--- Sent from the ${APP_NAME} feedback button ---`);
  return lines.join("\n");
}

export type FeedbackDeliveryStatus =
  /** A relay answered 2xx. The only outcome that may be called "sent". */
  | "sent"
  /** The note was handed to a mail client. Nothing can confirm what follows. */
  | "handed-off"
  /** Neither path got anywhere. The copy panel is now the delivery route. */
  | "failed";

export type FeedbackDelivery = {
  status: FeedbackDeliveryStatus;
  /** One sentence for the visitor, saying what actually happened. */
  detail: string;
  subject: string;
  body: string;
  to: string;
};

export function mailtoUrl(to: string, subject: string, body: string): string {
  return `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/**
 * Try the relay when it is configured, otherwise the mail client; a relay that
 * errors falls through to the mail client and says why, so a transport failure
 * never eats the note.
 */
export async function deliverNote(note: FeedbackNote): Promise<FeedbackDelivery> {
  const to = feedbackEmail();
  const subject = composeSubject(note);
  const body = composeBody(note);
  const base = { subject, body, to };
  const relay = feedbackRelayUrl();

  if (relay) {
    const outcome = await postToRelay(relay, note, subject, body);
    if (outcome.ok) {
      return { ...base, status: "sent", detail: `Sent — it is in ${to}. Thank you.` };
    }
    const fallback = openMailClient(to, subject, body);
    return {
      ...base,
      status: fallback.opened ? "handed-off" : "failed",
      detail: fallback.opened
        ? `${outcome.detail} Your mail app should be opening instead — or copy the note below.`
        : `${outcome.detail} Your mail app did not open either, so please copy the note below.`,
    };
  }

  const handoff = openMailClient(to, subject, body);
  if (!handoff.opened) {
    return {
      ...base,
      status: "failed",
      detail: `Your mail app did not open (${handoff.detail}). Copy the note below and send it to ${to}.`,
    };
  }
  const longNote =
    mailtoUrl(to, subject, body).length > MAILTO_SAFE_LENGTH
      ? " It is a long note, so some mail apps trim it — the full text is below."
      : "";
  return {
    ...base,
    status: "handed-off",
    detail: `Your mail app should be opening with the note addressed to ${to}. Nothing is sent until you press send there.${longNote}`,
  };
}

async function postToRelay(
  url: string,
  note: FeedbackNote,
  subject: string,
  body: string,
): Promise<{ ok: true } | { ok: false; detail: string }> {
  const key = feedbackRelayKey();
  const payload: Record<string, string> = {
    subject,
    message: body,
    from_name: `${APP_NAME} feedback`,
    category: note.category.subject,
  };
  if (note.replyTo.trim()) payload.replyto = note.replyTo.trim();
  if (key) payload.access_key = key;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) return { ok: true };
    return { ok: false, detail: `The feedback relay refused the note (HTTP ${res.status}).` };
  } catch (err) {
    // Offline, DNS, CORS, blocked by an extension — all the same to the visitor.
    const why = err instanceof Error && err.message ? err.message : "network error";
    return { ok: false, detail: `The feedback relay could not be reached (${why}).` };
  }
}

/**
 * Assigning `location.href` rather than `window.open`: a popup blocker eats the
 * second one silently, which is the exact failure this feature must not have.
 */
function openMailClient(
  to: string,
  subject: string,
  body: string,
): { opened: boolean; detail: string } {
  try {
    if (typeof window === "undefined") return { opened: false, detail: "no browser window" };
    window.location.href = mailtoUrl(to, subject, body);
    return { opened: true, detail: "" };
  } catch (err) {
    const why = err instanceof Error && err.message ? err.message : "unknown error";
    return { opened: false, detail: why };
  }
}
