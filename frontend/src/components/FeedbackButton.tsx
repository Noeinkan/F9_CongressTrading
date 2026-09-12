import {
  Accordion,
  Alert,
  Anchor,
  Box,
  Button,
  Checkbox,
  Code,
  Collapse,
  CopyButton,
  Group,
  Modal,
  Stack,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  DEFAULT_CATEGORY,
  FEEDBACK_CATEGORIES,
  MAX_MESSAGE_LENGTH,
  categoryById,
  collectContext,
  deliverNote,
  feedbackEmail,
  mailtoUrl,
  validateNote,
  type FeedbackCategoryId,
  type FeedbackDelivery,
} from "@/utils/feedback";

/**
 * Top-bar "Feedback" trigger and the modal behind it.
 *
 * The shape of the form is deliberate: categories as an accordion (opening one
 * both picks it and shows what a useful note of that kind contains), a single
 * shared message box (switching category must never eat what you typed), the
 * placeholder as a fill-in template, and the reply address optional.
 *
 * Delivery, validation and composing live in `utils/feedback.ts`. Whatever the
 * outcome, the composed note is rendered back here for copying — see the
 * "note must never vanish" comment in that module.
 */
export function FeedbackButton() {
  const [opened, { open, close }] = useDisclosure(false);
  const location = useLocation();
  const route = `${location.pathname}${location.search}`;

  /**
   * Two pieces of state, not one: `openId` is which accordion panel is
   * expanded (null when they are all shut), `categoryId` is the choice. A
   * collapsed accordion reports `null`, and that must not wipe the selection
   * halfway through composing.
   */
  const [openId, setOpenId] = useState<string | null>(DEFAULT_CATEGORY.id);
  const [categoryId, setCategoryId] = useState<FeedbackCategoryId>(DEFAULT_CATEGORY.id);
  const category = categoryById(categoryId);

  const [message, setMessage] = useState("");
  const [replyTo, setReplyTo] = useState("");
  const [attachContext, setAttachContext] = useState(true);
  const [contextShown, setContextShown] = useState(false);
  const [sending, setSending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [result, setResult] = useState<FeedbackDelivery | null>(null);

  const to = feedbackEmail();
  // Read on every render rather than memoised: the rows on screen are then
  // always the ones that will be sent, never a stale snapshot.
  const context = collectContext(route);

  const statusRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!problem && !result) return;
    // In a tall modal with a pinned footer the status line renders below the
    // fold, which looks identical to a button that did nothing.
    statusRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [problem, result]);

  function handleCategory(next: string | null) {
    setOpenId(next);
    if (next) setCategoryId(next as FeedbackCategoryId);
  }

  async function handleSend() {
    const reason = validateNote({ message, replyTo });
    setResult(null);
    if (reason) {
      setProblem(reason);
      return;
    }
    setProblem(null);
    setSending(true);
    const delivery = await deliverNote({
      category,
      message,
      replyTo,
      context: attachContext ? context : null,
      sentAt: new Date(),
    });
    setSending(false);
    setResult(delivery);
    // Only a confirmed delivery clears the draft; anything else and the text
    // stays put, because the copy panel is now the way it reaches the inbox.
    if (delivery.status === "sent") setMessage("");
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        className="feedback-button"
        title="Send feedback to the maintainer"
        aria-label="Send feedback to the maintainer"
        data-testid="topbar-feedback"
      >
        Feedback
      </button>

      <Modal
        opened={opened}
        onClose={close}
        title="Tell me what you think"
        size="lg"
        radius="md"
        data-testid="feedback-modal"
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Pick what kind of note this is — opening one shows what makes that kind useful.
            Nothing is required beyond the message itself.
          </Text>

          <Accordion value={openId} onChange={handleCategory} variant="separated" radius="sm">
            {FEEDBACK_CATEGORIES.map((item) => (
              <Accordion.Item key={item.id} value={item.id}>
                <Accordion.Control data-testid={`feedback-category-${item.id}`}>
                  <Group gap="xs" wrap="nowrap">
                    <Text component="span" aria-hidden>
                      {item.emoji}
                    </Text>
                    <Text
                      component="span"
                      size="sm"
                      fw={item.id === categoryId ? 700 : 500}
                    >
                      {item.label}
                    </Text>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Text size="xs" c="dimmed">
                    {item.hint}
                  </Text>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>

          <Textarea
            label="Your message"
            description={`Sending as: ${category.label}`}
            placeholder={category.placeholder}
            value={message}
            onChange={(e) => setMessage(e.currentTarget.value)}
            autosize
            minRows={6}
            maxRows={14}
            maxLength={MAX_MESSAGE_LENGTH}
            data-testid="feedback-message"
          />
          <Text size="xs" c="dimmed" ta="right" mt={-8}>
            {message.length} / {MAX_MESSAGE_LENGTH}
          </Text>

          <TextInput
            label="Email, if you would like a reply"
            description="Leave blank to stay anonymous — an anonymous note is still a good note."
            placeholder="you@example.com"
            type="email"
            value={replyTo}
            onChange={(e) => setReplyTo(e.currentTarget.value)}
            data-testid="feedback-reply"
          />

          <Box>
            <Checkbox
              checked={attachContext}
              onChange={(e) => setAttachContext(e.currentTarget.checked)}
              label="Attach technical context (which page, app version, browser)"
              data-testid="feedback-context-toggle"
            />
            <Anchor
              component="button"
              type="button"
              size="xs"
              onClick={() => setContextShown((v) => !v)}
              mt={6}
              data-testid="feedback-context-disclosure"
            >
              {contextShown ? "Hide what that attaches" : "Show exactly what that attaches"}
            </Anchor>
            <Collapse in={contextShown}>
              <Stack gap={2} mt={8} data-testid="feedback-context-rows">
                {context.map((row) => (
                  <Text key={row.label} size="xs" c="dimmed" style={{ wordBreak: "break-word" }}>
                    <strong>{row.label}:</strong> {row.value}
                  </Text>
                ))}
                <Text size="xs" c="dimmed" mt={4}>
                  Nothing beyond what you can read here — no account name, no file paths, no
                  stored data.
                </Text>
              </Stack>
            </Collapse>
          </Box>

          <div ref={statusRef}>
            {problem ? (
              <Alert color="orange" variant="light" data-testid="feedback-status">
                {problem}
              </Alert>
            ) : null}
            {result ? (
              <Alert
                color={result.status === "sent" ? "teal" : result.status === "failed" ? "red" : "blue"}
                variant="light"
                data-testid="feedback-status"
              >
                {result.detail}
              </Alert>
            ) : null}
          </div>

          {/* Above the action row on purpose: below it, the copy-out panel
              sits off the bottom of the modal and the one thing that rescues a
              failed send is the thing nobody scrolls to. */}
          {result ? <ComposedNote result={result} /> : null}

          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              Goes to {to}
            </Text>
            <Group gap="sm">
              <Button variant="subtle" color="gray" onClick={close}>
                Close
              </Button>
              <Button onClick={handleSend} loading={sending} data-testid="feedback-send">
                Send feedback
              </Button>
            </Group>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

/**
 * The copy-out panel. This is the part that makes a silent failure
 * recoverable: whatever the transport did, the exact text and the address it
 * belongs to are on screen.
 */
function ComposedNote({ result }: { result: FeedbackDelivery }) {
  const full = `To: ${result.to}\nSubject: ${result.subject}\n\n${result.body}`;
  return (
    <Stack gap="xs" data-testid="feedback-composed">
      <Text size="sm" fw={600}>
        {result.status === "sent" ? "A copy of what was sent" : "Your note — copy it if needed"}
      </Text>
      <Text size="xs" c="dimmed">
        {result.status === "sent"
          ? "Keep this if you want a record of it."
          : `If your mail app did not open, paste this into an email to ${result.to}.`}
      </Text>
      <Code
        block
        style={{ maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap", fontSize: 12 }}
      >
        {full}
      </Code>
      <Group gap="sm">
        <CopyButton value={full}>
          {({ copied, copy }) => (
            <Button size="xs" variant="light" onClick={copy} data-testid="feedback-copy">
              {copied ? "Copied" : "Copy the note"}
            </Button>
          )}
        </CopyButton>
        <Anchor
          size="xs"
          href={mailtoUrl(result.to, result.subject, result.body)}
          data-testid="feedback-mailto"
        >
          Open in my mail app
        </Anchor>
      </Group>
    </Stack>
  );
}
