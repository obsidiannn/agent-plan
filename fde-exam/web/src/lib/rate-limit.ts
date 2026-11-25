type Bucket = {
  count: number;
  resetAt: number;
};

const buckets = new Map<string, Bucket>();
const LOGIN_LIMIT = 8;
const LOGIN_WINDOW_MS = 60_000;

export function loginKey(request: Request, username: string) {
  const forwarded = request.headers.get("x-forwarded-for") || "";
  const ip = forwarded.split(",")[0].trim() || "local";
  return `${ip}:${username.toLowerCase()}`;
}

export function checkLoginLimit(key: string): {
  allowed: boolean;
  retryAfter: number;
} {
  const now = Date.now();
  const bucket = buckets.get(key);
  if (!bucket || bucket.resetAt <= now) {
    return { allowed: true, retryAfter: 0 };
  }
  if (bucket.count < LOGIN_LIMIT) {
    return { allowed: true, retryAfter: 0 };
  }
  return {
    allowed: false,
    retryAfter: Math.ceil((bucket.resetAt - now) / 1000),
  };
}

export function recordLoginFailure(key: string) {
  const now = Date.now();
  const bucket = buckets.get(key);
  if (!bucket || bucket.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + LOGIN_WINDOW_MS });
    return;
  }
  bucket.count += 1;
  if (buckets.size > 5000) {
    for (const [k, value] of buckets) {
      if (value.resetAt <= now) buckets.delete(k);
    }
  }
}

export function clearLoginFailures(key: string) {
  buckets.delete(key);
}
