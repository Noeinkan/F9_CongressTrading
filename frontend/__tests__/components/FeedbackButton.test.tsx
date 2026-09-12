import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FeedbackButton } from "@/components/FeedbackButton";
import { collectContext, composeBody, validateNote, FEEDBACK_CATEGORIES } from "@/utils/feedback";

/**
 * jsdom refuses real navigation, so `window.location.href = "mailto:…"` would
 * only print an "unimplemented" warning and tell us nothing. Swap in a plain
 * object and the mail hand-off becomes observable.
 */
let hrefSet: string[] = [];
let realLocation: Location;

function stubLocation() {
  realLocation = window.location;
  hrefSet = [];
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: {
      ...realLocation,
      get href() {
        return hrefSet.at(-1) ?? "http://localhost/";
      },
      set href(value: string) {
        hrefSet.push(value);
      },
    },
  });
}

function restoreLocation() {
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: realLocation,
  });
}

function renderButton() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/members?lookback=12"]}>
        <FeedbackButton />
      </MemoryRouter>
    </MantineProvider>,
  );
}

/**
 * `delay: null` removes userEvent's inter-keystroke wait. With the default,
 * typing a sentence into a Mantine autosize textarea re-renders per character
 * and these tests overrun the 5s timeout once the whole suite is competing for
 * the CPU. Real key events are still dispatched, just without the pauses.
 */
async function openModal() {
  const user = userEvent.setup({ delay: null });
  renderButton();
  await user.click(screen.getByTestId("topbar-feedback"));
  await screen.findByTestId("feedback-message");
  return user;
}

/** One paste event instead of one render per character. */
async function writeMessage(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.click(screen.getByTestId("feedback-message"));
  await user.paste(text);
}

beforeEach(() => {
  stubLocation();
});

afterEach(() => {
  restoreLocation();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("FeedbackButton trigger", () => {
  it("renders a Feedback trigger in the header and opens the modal", async () => {
    const user = userEvent.setup();
    renderButton();
    const trigger = screen.getByTestId("topbar-feedback");
    expect(trigger).toHaveTextContent("Feedback");
    expect(trigger).toHaveAttribute("aria-label", "Send feedback to the maintainer");

    await user.click(trigger);
    expect(await screen.findByTestId("feedback-message")).toBeInTheDocument();
    // The destination is on screen before anything is sent.
    expect(screen.getByText(/Goes to .+@.+/)).toBeInTheDocument();
  });
});

describe("validation says why, not just no", () => {
  it("refuses an empty message with a reason", async () => {
    const user = await openModal();
    await user.click(screen.getByTestId("feedback-send"));
    expect(await screen.findByTestId("feedback-status")).toHaveTextContent(
      /message box is empty/i,
    );
    expect(screen.queryByTestId("feedback-composed")).not.toBeInTheDocument();
  });

  it("refuses a two-word message with a reason", async () => {
    const user = await openModal();
    await user.type(screen.getByTestId("feedback-message"), "broken");
    await user.click(screen.getByTestId("feedback-send"));
    expect(await screen.findByTestId("feedback-status")).toHaveTextContent(/few more words/i);
  });

  it("refuses a malformed reply address and points at the anonymous option", () => {
    expect(validateNote({ message: "a".repeat(20), replyTo: "nope@" })).toMatch(
      /does not look like an email.*anonymous/i,
    );
    expect(validateNote({ message: "a".repeat(20), replyTo: "" })).toBeNull();
    expect(validateNote({ message: "a".repeat(20), replyTo: "me@example.com" })).toBeNull();
  });
});

describe("category selection", () => {
  it("keeps typed text and swaps the placeholder when the category changes", async () => {
    const user = await openModal();
    const box = screen.getByTestId("feedback-message");
    await writeMessage(user, "The Members KPI row disagrees with the filing PDF.");
    expect(box).toHaveAttribute("placeholder", expect.stringContaining("What happened instead"));

    await user.click(screen.getByTestId("feedback-category-data"));

    // Text survives the switch; only the template changes.
    expect(box).toHaveValue("The Members KPI row disagrees with the filing PDF.");
    await waitFor(() =>
      expect(box).toHaveAttribute(
        "placeholder",
        expect.stringContaining("Which number looks wrong"),
      ),
    );
  });

  it("keeps the last real choice when the accordion is collapsed", async () => {
    const user = await openModal();
    await user.click(screen.getByTestId("feedback-category-idea"));
    expect(await screen.findByText(/Sending as: I have an idea/)).toBeInTheDocument();

    // Clicking the open control again collapses the panel and reports null.
    await user.click(screen.getByTestId("feedback-category-idea"));
    expect(screen.getByText(/Sending as: I have an idea/)).toBeInTheDocument();
  });
});

describe("delivery", () => {
  it("never claims 'sent' for a mailto hand-off, and shows the note", async () => {
    const user = await openModal();
    await writeMessage(user, "The sector heatmap renders empty for Q1 2026.");
    await user.click(screen.getByTestId("feedback-send"));

    const status = await screen.findByTestId("feedback-status");
    expect(status).toHaveTextContent(/mail app should be opening/i);
    // No claim of delivery: only a relay 2xx earns that. "Nothing is sent
    // until you press send there" is the honest disclaimer, so the check is
    // aimed at the claiming forms rather than the word itself.
    expect(status.textContent ?? "").not.toMatch(/^sent\b|\b(was|has been|we) sent\b/i);
    expect(status).toHaveTextContent(/Nothing is sent until you press send/i);

    // The hand-off actually happened, with the note in the URL.
    expect(hrefSet.at(-1) ?? "").toMatch(/^mailto:[^?]+\?subject=/);
    expect(decodeURIComponent(hrefSet.at(-1) ?? "")).toContain("sector heatmap renders empty");

    // Rule zero: the composed text is on screen regardless.
    expect(screen.getByTestId("feedback-composed")).toBeInTheDocument();
  });

  it("says sent only when a relay answers 2xx", async () => {
    vi.stubEnv("VITE_FEEDBACK_RELAY_URL", "https://relay.example/submit");
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200 }) as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    const user = await openModal();
    await writeMessage(user, "Add a CSV export to the Tickers table.");
    await user.click(screen.getByTestId("feedback-send"));

    expect(await screen.findByTestId("feedback-status")).toHaveTextContent(/^Sent —/);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(hrefSet).toHaveLength(0); // no mail client needed
  });

  it("falls through to the mail client when the relay fails, and says why", async () => {
    vi.stubEnv("VITE_FEEDBACK_RELAY_URL", "https://relay.example/submit");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 502 }) as unknown as Response),
    );

    const user = await openModal();
    await writeMessage(user, "Login bounces back to the form on Safari.");
    await user.click(screen.getByTestId("feedback-send"));

    const status = await screen.findByTestId("feedback-status");
    expect(status).toHaveTextContent(/HTTP 502/);
    expect(status).toHaveTextContent(/mail app should be opening/i);
    expect(hrefSet.at(-1) ?? "").toMatch(/^mailto:/);
    expect(screen.getByTestId("feedback-composed")).toBeInTheDocument();
  });

  it("does not raise when the relay throws, it still delivers the note", async () => {
    vi.stubEnv("VITE_FEEDBACK_RELAY_URL", "https://relay.example/submit");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("Failed to fetch");
      }),
    );

    const user = await openModal();
    await writeMessage(user, "Charts stall on slow connections.");
    await user.click(screen.getByTestId("feedback-send"));

    expect(await screen.findByTestId("feedback-status")).toHaveTextContent(
      /could not be reached \(Failed to fetch\)/,
    );
    expect(screen.getByTestId("feedback-composed")).toBeInTheDocument();
  });
});

describe("context attachment keeps its promise", () => {
  it("collects only the boring facts the modal displays", () => {
    const labels = collectContext("/members?lookback=12").map((row) => row.label);
    // An allowlist, so a later edit that adds a field has to come through here.
    expect(labels).toEqual(["Page", "App version", "React", "Browser / OS", "Viewport"]);
  });

  it("leaks no account name, path or stored value into the body", () => {
    window.localStorage.setItem("congress.session", "secret-token-value");
    const body = composeBody({
      category: FEEDBACK_CATEGORIES[0],
      message: "Something is broken on the Raw Data page.",
      replyTo: "",
      context: collectContext("/raw"),
      sentAt: new Date("2026-09-12T14:03:00"),
    });

    expect(body).toContain("Reply: not given (anonymous)");
    expect(body).toContain("--- Context ---");
    expect(body).toContain("Page");
    expect(body).not.toContain("secret-token-value");
    expect(body).not.toMatch(/[A-Za-z]:\\Users\\/); // no Windows home path
    expect(body).not.toMatch(/\/(home|Users)\//); // no POSIX home path
    expect(body).not.toMatch(/localStorage|token|cookie|hostname/i);
  });

  it("omits the context block entirely when the visitor clears the checkbox", async () => {
    const user = await openModal();
    await user.click(screen.getByTestId("feedback-context-toggle"));
    await writeMessage(user, "The period filter resets when I switch pages.");
    await user.click(screen.getByTestId("feedback-send"));

    await screen.findByTestId("feedback-composed");
    expect(screen.getByTestId("feedback-composed").textContent ?? "").not.toContain(
      "--- Context ---",
    );
  });

  it("shows the live values behind the checkbox on request", async () => {
    const user = await openModal();
    await user.click(screen.getByTestId("feedback-context-disclosure"));
    const rows = await screen.findByTestId("feedback-context-rows");
    expect(rows).toHaveTextContent("/members?lookback=12");
    expect(rows).toHaveTextContent("React:");
  });
});

describe("subject line", () => {
  it("stays ASCII so mail clients don't mangle it", async () => {
    const user = await openModal();
    await writeMessage(user, "A perfectly ordinary bug report.");
    await user.click(screen.getByTestId("feedback-send"));

    const url = decodeURIComponent(hrefSet.at(-1) ?? "");
    const subject = url.slice(url.indexOf("subject=") + 8, url.indexOf("&body="));
    expect(subject).toBe("[Congress Trading] Bug report");
    expect(subject).toMatch(/^[\x20-\x7e]+$/);
  });
});
