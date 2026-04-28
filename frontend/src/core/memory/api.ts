import { fetch } from "../api/fetcher";
import { getBackendBaseURL } from "../config";

import type {
  MemoryFactInput,
  MemoryFactPatchInput,
  UserMemory,
} from "./types";

function getUserId(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("user_id");
  }
  return null;
}

async function readMemoryResponse(
  response: Response,
  fallbackMessage: string,
): Promise<UserMemory> {
  function formatErrorDetail(detail: unknown): string | null {
    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }

          if (item && typeof item === "object") {
            const record = item as Record<string, unknown>;
            if (typeof record.msg === "string") {
              return record.msg;
            }

            try {
              return JSON.stringify(record);
            } catch {
              return null;
            }
          }

          return String(item);
        })
        .filter(Boolean);

      return parts.length > 0 ? parts.join("; ") : null;
    }

    if (detail && typeof detail === "object") {
      try {
        return JSON.stringify(detail);
      } catch {
        return null;
      }
    }

    if (
      typeof detail === "string" ||
      typeof detail === "number" ||
      typeof detail === "boolean" ||
      typeof detail === "bigint"
    ) {
      return String(detail);
    }

    if (typeof detail === "symbol") {
      return detail.description ?? null;
    }

    return null;
  }

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: unknown;
    };
    const detailMessage = formatErrorDetail(errorData.detail);
    throw new Error(
      detailMessage ?? `${fallbackMessage}: ${response.statusText}`,
    );
  }

  return response.json() as Promise<UserMemory>;
}

function buildUrlWithUserId(url: string): string {
  const userId = getUserId();
  if (userId) {
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}user_id=${encodeURIComponent(userId)}`;
  }
  return url;
}

export async function loadMemory(): Promise<UserMemory> {
  const url = buildUrlWithUserId(`${getBackendBaseURL()}/api/memory`);
  const response = await fetch(url);
  return readMemoryResponse(response, "Failed to fetch memory");
}

export async function clearMemory(): Promise<UserMemory> {
  const url = buildUrlWithUserId(`${getBackendBaseURL()}/api/memory`);
  const response = await fetch(url, {
    method: "DELETE",
  });
  return readMemoryResponse(response, "Failed to clear memory");
}

export async function deleteMemoryFact(factId: string): Promise<UserMemory> {
  const url = buildUrlWithUserId(
    `${getBackendBaseURL()}/api/memory/facts/${encodeURIComponent(factId)}`,
  );
  const response = await fetch(url, {
    method: "DELETE",
  });
  return readMemoryResponse(response, "Failed to delete memory fact");
}

export async function exportMemory(): Promise<UserMemory> {
  const url = buildUrlWithUserId(`${getBackendBaseURL()}/api/memory/export`);
  const response = await fetch(url);
  return readMemoryResponse(response, "Failed to export memory");
}

export async function importMemory(memory: UserMemory): Promise<UserMemory> {
  const url = buildUrlWithUserId(`${getBackendBaseURL()}/api/memory/import`);
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(memory),
  });
  return readMemoryResponse(response, "Failed to import memory");
}

export async function createMemoryFact(
  input: MemoryFactInput,
): Promise<UserMemory> {
  const url = buildUrlWithUserId(`${getBackendBaseURL()}/api/memory/facts`);
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
  return readMemoryResponse(response, "Failed to create memory fact");
}

export async function updateMemoryFact(
  factId: string,
  input: MemoryFactPatchInput,
): Promise<UserMemory> {
  const url = buildUrlWithUserId(
    `${getBackendBaseURL()}/api/memory/facts/${encodeURIComponent(factId)}`,
  );
  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
  return readMemoryResponse(response, "Failed to update memory fact");
}
