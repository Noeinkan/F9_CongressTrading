import { Alert, Anchor, Button, Center, Paper, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { demoQueryKey, useDemoAccessCode, useDemoAccessRequest, useDemoStatus } from "@/api/demo";

/**
 * Same-site paths only: `next` comes from a query string an attacker could
 * craft, so anything that would leave this origin (`//host/...`) or the
 * legacy backslash trick browsers still treat as a scheme separator
 * (`/\host/...`) falls back to the default. Landing back inside `/access`
 * itself would loop the sign-in flow, so that is refused too.
 */
function safeNext(raw: string | null): string {
  if (!raw) return "/";
  if (!raw.startsWith("/")) return "/";
  if (raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  if (raw === "/access" || raw.startsWith("/access/") || raw.startsWith("/access?")) return "/";
  return raw;
}

function errorDetail(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.body && typeof err.body === "object") {
    const detail = (err.body as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

function errorCode(err: unknown): string | null {
  if (err instanceof ApiError && err.body && typeof err.body === "object") {
    const code = (err.body as Record<string, unknown>).code;
    if (typeof code === "string") return code;
  }
  return null;
}

type CodeError = {
  detail: string;
  attemptsLeft?: number;
  dead?: boolean;
};

export function Access() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const status = useDemoStatus();
  const nextPath = useMemo(() => safeNext(searchParams.get("next")), [searchParams]);

  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [requestError, setRequestError] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<CodeError | null>(null);

  const requestMutation = useDemoAccessRequest();
  const codeMutation = useDemoAccessCode();

  const minutes = status.data?.session?.minutes ?? 45;
  const snapshotLabel = status.data?.snapshotLabel;
  const codeMinutes = status.data?.access?.codeMinutes ?? 15;
  const privacy = status.data?.access?.privacy ?? [];

  const backToEmail = () => {
    setStep("email");
    setCode("");
    setCodeError(null);
  };

  const handleRequestSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setRequestError(null);
    try {
      await requestMutation.mutateAsync(email.trim());
      setStep("code");
    } catch (err) {
      setRequestError(errorDetail(err, "Could not send the code. Try again in a moment."));
    }
  };

  const handleCodeSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setCodeError(null);
    try {
      await codeMutation.mutateAsync({ email: email.trim(), code: code.trim() });
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
      navigate(nextPath, { replace: true });
    } catch (err) {
      const kind = errorCode(err);
      if (kind === "DEMO_EXPIRED") {
        navigate("/access/ended");
        return;
      }
      if (kind === "WRONG_CODE" && err instanceof ApiError && err.body && typeof err.body === "object") {
        const attemptsLeft = (err.body as Record<string, unknown>).attemptsLeft;
        setCodeError({
          detail: errorDetail(err, "That code did not work."),
          attemptsLeft: typeof attemptsLeft === "number" ? attemptsLeft : undefined,
        });
        return;
      }
      if (kind === "CODE_DEAD") {
        setCodeError({ detail: errorDetail(err, "That code no longer works."), dead: true });
        return;
      }
      setCodeError({ detail: errorDetail(err, "That code did not work.") });
    }
  };

  return (
    <Center h="100vh" p="md">
      <Paper p="xl" radius="md" shadow="sm" withBorder w={440} maw="100%">
        {step === "email" ? (
          <Stack gap="md" data-testid="access-email-step">
            <Stack gap={4}>
              <Title order={3}>Try the Congressional Disclosure Tracker free for {minutes} minutes</Title>
              <Text size="sm" c="dimmed">
                Read-only dashboards over a frozen snapshot
                {snapshotLabel ? ` — ${snapshotLabel}` : ""}. No password, no card.
              </Text>
            </Stack>
            {requestError ? (
              <Alert color="red" title="Could not send the code" data-testid="access-request-error">
                {requestError}
              </Alert>
            ) : null}
            <form onSubmit={handleRequestSubmit} data-testid="access-email-form">
              <Stack gap="sm">
                <TextInput
                  label="Work email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.currentTarget.value)}
                  autoComplete="email"
                  required
                  data-testid="access-email-input"
                />
                <Button
                  type="submit"
                  loading={requestMutation.isPending}
                  disabled={requestMutation.isPending || !email.trim()}
                  data-testid="access-email-submit"
                >
                  Send me a code
                </Button>
              </Stack>
            </form>
            {privacy.length ? (
              <Stack gap={4}>
                {privacy.map((paragraph) => (
                  <Text key={paragraph.title} size="xs" c="dimmed">
                    <Text span fw={700}>
                      {paragraph.title}
                    </Text>{" "}
                    {paragraph.text}
                  </Text>
                ))}
              </Stack>
            ) : null}
          </Stack>
        ) : (
          <Stack gap="md" data-testid="access-code-step">
            <Stack gap={4}>
              <Title order={3}>Check your inbox</Title>
              <Text size="sm">
                If {email} can receive mail, a 6-digit code is on its way. Type it below, or open the
                link in the email. Both work for {codeMinutes} minutes.
              </Text>
            </Stack>
            {codeError ? (
              <Alert color="red" title="That didn't work" data-testid="access-code-error">
                <Stack gap={4}>
                  <Text size="sm">
                    {codeError.detail}
                    {typeof codeError.attemptsLeft === "number"
                      ? ` (${codeError.attemptsLeft} attempt${codeError.attemptsLeft === 1 ? "" : "s"} left)`
                      : ""}
                  </Text>
                  {codeError.dead ? (
                    <Anchor size="sm" onClick={backToEmail} data-testid="access-code-dead-retry">
                      Ask for a new code
                    </Anchor>
                  ) : null}
                </Stack>
              </Alert>
            ) : null}
            <form onSubmit={handleCodeSubmit} data-testid="access-code-form">
              <Stack gap="sm">
                <TextInput
                  label="6-digit code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={7}
                  value={code}
                  onChange={(event) => setCode(event.currentTarget.value)}
                  required
                  data-testid="access-code-input"
                />
                <Button
                  type="submit"
                  loading={codeMutation.isPending}
                  disabled={codeMutation.isPending || !code.trim()}
                  data-testid="access-code-submit"
                >
                  Continue
                </Button>
              </Stack>
            </form>
            <Anchor size="sm" onClick={backToEmail} data-testid="access-use-different-email">
              Use a different address
            </Anchor>
            <Text size="xs" c="dimmed">
              Nothing arrived? Check spam, then ask again in a minute.
            </Text>
          </Stack>
        )}
      </Paper>
    </Center>
  );
}
