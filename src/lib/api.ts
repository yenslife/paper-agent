const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function buildApiUrl(path: string, params?: URLSearchParams) {
  if (params) {
    return `${apiBaseUrl}${path}?${params.toString()}`;
  }
  return `${apiBaseUrl}${path}`;
}

export { apiBaseUrl };
