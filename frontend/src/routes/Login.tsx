import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Center,
  Loader,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useLogin, useSessionProbe } from "@/api/auth";

export function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useSessionProbe();
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const from =
    (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";

  useEffect(() => {
    if (session.data && (!session.data.auth_required || session.data.authenticated)) {
      navigate(from, { replace: true });
    }
  }, [session.data, navigate, from]);

  if (session.isLoading) {
    return (
      <Center h="100vh">
        <Stack align="center" gap="sm">
          <Loader size="md" />
          <Text c="dimmed">Checking session…</Text>
        </Stack>
      </Center>
    );
  }

  if (session.isError) {
    return (
      <Center h="100vh" p="md">
        <Paper p="xl" radius="md" shadow="sm" withBorder w={400} maw="100%">
          <Stack gap="md">
            <Title order={3}>Sign in</Title>
            <Alert color="red" title="Session probe failed">
              Could not reach <code>/api/session</code>. Make sure the FastAPI server is
              running on port 9001.
            </Alert>
            <Button variant="default" onClick={() => session.refetch()}>
              Try again
            </Button>
          </Stack>
        </Paper>
      </Center>
    );
  }

  if (!session.data) {
    return null;
  }

  if (!session.data.auth_required) {
    return <Navigate to="/" replace />;
  }

  if (session.data.authenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ username, password });
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid username or password.");
        setPassword("");
      } else {
        setError("Login failed. Please try again.");
      }
    }
  };

  return (
    <Center h="100vh" p="md">
      <Paper p="xl" radius="md" shadow="sm" withBorder w={400} maw="100%">
        <form onSubmit={handleSubmit} data-testid="login-form">
          <Stack gap="md">
            <Stack gap={4}>
              <Title order={3}>Sign in</Title>
              <Text size="sm" c="dimmed">
                Congress Trading dashboard
              </Text>
            </Stack>
            {error ? (
              <Alert color="red" title="Login failed" data-testid="login-error">
                {error}
              </Alert>
            ) : null}
            <TextInput
              label="Username"
              value={username}
              onChange={(event) => setUsername(event.currentTarget.value)}
              autoComplete="username"
              required
              data-testid="login-username"
            />
            <PasswordInput
              label="Password"
              value={password}
              onChange={(event) => setPassword(event.currentTarget.value)}
              autoComplete="current-password"
              required
              data-testid="login-password"
            />
            <Button
              type="submit"
              loading={login.isPending}
              disabled={login.isPending || !username || !password}
              data-testid="login-submit"
            >
              Sign in
            </Button>
            <Text size="xs" c="dimmed" ta="center">
              <Link to="/">Back to dashboard</Link>
            </Text>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
