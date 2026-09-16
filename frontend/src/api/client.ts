export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

/** The four refusal codes any `/api/*` call can answer with once the demo gate is on. */
export type DemoRefusalCode =
  | "DEMO_SIGNED_OUT"
  | "DEMO_EXPIRED"
  | "DEMO_LOCKED"
  | "DEMO_READ_ONLY";

export type DemoRefusalBody = {
  code: DemoRefusalCode;
  detail?: string;
  message?: string;
  feature?: string;
  revoked?: boolean;
  contactEmail?: string;
  demo?: boolean;
  readOnly?: boolean;
};

const DEMO_REFUSAL_CODES: ReadonlySet<string> = new Set([
  "DEMO_SIGNED_OUT",
  "DEMO_EXPIRED",
  "DEMO_LOCKED",
  "DEMO_READ_ONLY",
]);

function isDemoRefusalBody(value: unknown): value is DemoRefusalBody {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    DEMO_REFUSAL_CODES.has((value as Record<string, unknown>).code as string)
  );
}

type DemoRefusalListener = (body: DemoRefusalBody) => void;

/**
 * One wall for every demo refusal: every `/api/*` call that comes back with a
 * `DEMO_*` code runs through here, whether the refusal actually came from the
 * server or was raised client-side (a locked control opening the wall without
 * a round trip — see `useDemoLock`). `DemoWall` is the single subscriber that
 * turns this into UI; nothing else needs to know the transport.
 */
const demoRefusalListeners = new Set<DemoRefusalListener>();

export function onDemoRefusal(listener: DemoRefusalListener): () => void {
  demoRefusalListeners.add(listener);
  return () => {
    demoRefusalListeners.delete(listener);
  };
}

export function emitDemoRefusal(body: DemoRefusalBody): void {
  demoRefusalListeners.forEach((listener) => listener(body));
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  return text.length ? text : null;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options;
  const init: RequestInit = {
    credentials: "include",
    ...rest,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };

  const response = await fetch(path, init);
  const parsed = await parseBody(response);

  if (!response.ok) {
    if (isDemoRefusalBody(parsed)) {
      emitDemoRefusal(parsed);
    }
    throw new ApiError(response.status, parsed);
  }

  return parsed as T;
}
