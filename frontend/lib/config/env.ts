function required(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value.replace(/\/$/, "");
}

export const env = {
  apiBaseUrl: required("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000/api/v1"),
  apiOrigin: required("NEXT_PUBLIC_API_ORIGIN", "http://localhost:8000"),
  wsUrl: required("NEXT_PUBLIC_WS_URL", "ws://localhost:8000/api/v1/ws/events"),
};
