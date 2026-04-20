function getLawLibraryApiBase(): string {
  const configuredBase = process.env.NEXT_PUBLIC_KF_API_BASE_URL;
  if (configuredBase) {
    return configuredBase;
  }

  const backendBase = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
  if (backendBase) {
    return backendBase;
  }

  if (typeof window !== "undefined") {
    return `${window.location.origin}/api`;
  }

  return "http://localhost:4026/api";
}

export function buildLawLibraryUrl(
  path: string,
  params?: Record<string, string | number | undefined>
): string {
  const base = getLawLibraryApiBase().replace(/\/+$/, "");
  const cleanPath = path.replace(/^\/+/, "");
  let url = `${base}/${cleanPath}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        searchParams.set(key, String(value));
      }
    });

    const query = searchParams.toString();
    if (query) {
      url += `?${query}`;
    }
  }

  return url;
}
