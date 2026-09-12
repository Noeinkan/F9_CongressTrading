import { Button, Group, Stack, Text } from "@mantine/core";

import { useSendDigest } from "@/api/refresh";

export type TelegramSummary = {
  text: string;
  failed: boolean;
  /** A digest had gone out recently, so this refresh held its own back. */
  digestHeldBack: boolean;
  digestSentAt: string | null;
};

function stepStatus(steps: Record<string, unknown>, key: string): string | null {
  return typeof steps[key] === "string" ? ((steps[key] as string).split(" - ")[0] ?? null) : null;
}

/** Derive the sidebar line from the refresh job's `result.post_ingest`. */
export function telegramSummary(postIngest: unknown): TelegramSummary | null {
  if (!postIngest || typeof postIngest !== "object") return null;
  const steps = postIngest as Record<string, unknown>;
  const alerts = stepStatus(steps, "alerts");
  const digest = stepStatus(steps, "digest");
  if (!alerts && !digest) return null;
  const digestText = typeof steps.digest === "string" ? steps.digest : "";
  const sentAt =
    typeof steps.digest_sent_at === "string" && steps.digest_sent_at ? steps.digest_sent_at : null;
  const digestHeldBack = digest === "skipped" && digestText.includes("already sent");
  let digestLabel = digest ?? "?";
  if (digestHeldBack) digestLabel = "not repeated";
  else if (digest === "sent" && sentAt) digestLabel = `sent ${formatSentAt(sentAt)}`;
  return {
    text: `Telegram — alerts: ${alerts ?? "?"} · digest: ${digestLabel}`,
    failed: [alerts, digest, stepStatus(steps, "exports")].includes("failed"),
    digestHeldBack,
    digestSentAt: sentAt,
  };
}

/** "today at 14:02" / "on 11 Sep at 14:02", in the viewer's time zone. */
export function formatSentAt(iso: string, now: Date = new Date()): string {
  const sent = new Date(iso);
  if (Number.isNaN(sent.getTime())) return "recently";
  const time = sent.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (sent.toDateString() === now.toDateString()) return `today at ${time}`;
  const day = sent.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  return `on ${day} at ${time}`;
}

export function TelegramRefreshSummary({ summary }: { summary: TelegramSummary }) {
  const sendDigest = useSendDigest();
  const resendFailed =
    sendDigest.isError || (sendDigest.data != null && sendDigest.data.status === "failed");

  return (
    <Stack gap={2} data-testid="refresh-telegram-summary">
      <Text size="xs" c={summary.failed ? "red" : "teal"}>
        {summary.text}
      </Text>
      {summary.digestHeldBack ? (
        <Group gap={6} wrap="wrap" data-testid="refresh-digest-held-back">
          <Text size="xs" c="dimmed">
            A digest already went out{" "}
            {summary.digestSentAt ? formatSentAt(summary.digestSentAt) : "recently"}, so this
            refresh did not send another.
          </Text>
          <Button
            size="compact-xs"
            variant="light"
            color="navy"
            loading={sendDigest.isPending}
            onClick={() => sendDigest.mutate()}
            data-testid="refresh-digest-resend"
          >
            Send digest again
          </Button>
        </Group>
      ) : null}
      {resendFailed ? (
        <Text size="xs" c="red" data-testid="refresh-digest-resend-error">
          Digest not sent:{" "}
          {sendDigest.data?.message ??
            (sendDigest.error instanceof Error ? sendDigest.error.message : "request failed")}
        </Text>
      ) : null}
    </Stack>
  );
}
