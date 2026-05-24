import { expect, test, describe, vi, beforeEach } from "vitest";

import { toCamelCase, toSnakeCase } from "@/extensions/project/transforms";

// Mock authFetch before importing api
vi.mock("@/extensions/api/client", () => ({
  authFetch: vi.fn(),
}));

import { projectApi } from "@/extensions/project/api";
import { authFetch } from "@/extensions/api/client";

const mockFetch = vi.mocked(authFetch);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("projectApi.list", () => {
  test("returns { items, total } with camelCase transform", async () => {
    const items = [
      { id: "p1", name: "Test", report_type: "other", status: "setup", current_stage: 1, chapter_count: 3, member_count: 2, template_name: "环评模板" },
    ];
    mockFetch.mockResolvedValueOnce({ items, total: 1 });

    const result = await projectApi.list();
    expect(result.total).toBe(1);
    expect(result.items[0].reportType).toBe("other");
    expect(result.items[0].chapterCount).toBe(3);
    expect(result.items[0].templateName).toBe("环评模板");
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("/projects?"));
  });

  test("passes filter params as query string", async () => {
    mockFetch.mockResolvedValueOnce({ items: [], total: 0 });

    await projectApi.list({ status: "writing", reportType: "environmental_impact", search: "test", skip: 5, limit: 10 });

    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain("status=writing");
    expect(url).toContain("report_type=environmental_impact");
    expect(url).toContain("search=test");
    expect(url).toContain("skip=5");
    expect(url).toContain("limit=10");
  });
});

describe("projectApi.get", () => {
  test("fetches and transforms to camelCase", async () => {
    const pid = "proj-123";
    mockFetch.mockResolvedValueOnce({
      id: pid,
      name: "Test",
      report_type: "other",
      current_stage: 2,
      created_at: "2024-01-01",
    });

    const result = await projectApi.get(pid);
    expect(result.id).toBe(pid);
    expect(result.reportType).toBe("other");
    expect(result.currentStage).toBe(2);
    expect(mockFetch).toHaveBeenCalledWith(`/project/projects/${pid}`);
  });
});

describe("projectApi.create", () => {
  test("POSTs with snake_case body and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      id: "new-1",
      name: "New Project",
      report_type: "environmental_impact",
      status: "setup",
    });

    const result = await projectApi.create({
      name: "New Project",
      reportType: "environmental_impact",
    });

    expect(result.reportType).toBe("environmental_impact");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("projectApi.delete", () => {
  test("sends DELETE request", async () => {
    mockFetch.mockResolvedValueOnce(undefined);

    await projectApi.delete("proj-1");
    expect(mockFetch).toHaveBeenCalledWith("/project/projects/proj-1", { method: "DELETE" });
  });
});

describe("projectApi.replaceOutline", () => {
  test("PUTs chapters array", async () => {
    const chapters = [
      { title: "Chapter 1", level: 1, sortOrder: 0, children: [] },
    ];
    mockFetch.mockResolvedValueOnce([]);

    await projectApi.replaceOutline("proj-1", chapters);
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/outline",
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining('"chapters"'),
      }),
    );
  });
});

describe("projectApi.confirmOutline", () => {
  test("POSTs to confirm-outline and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      id: "proj-1",
      name: "Test",
      report_type: "other",
      current_stage: 3,
      status: "writing",
    });

    const result = await projectApi.confirmOutline("proj-1");
    expect(result.currentStage).toBe(3);
    expect(result.status).toBe("writing");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/confirm-outline",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("projectApi.addMember", () => {
  test("POSTs member with snake_case body", async () => {
    mockFetch.mockResolvedValueOnce(undefined);

    await projectApi.addMember("proj-1", "user-1", "editor");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/members",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"user_id"'),
      }),
    );
  });
});

describe("projectApi.removeMember", () => {
  test("DELETEs member", async () => {
    mockFetch.mockResolvedValueOnce(undefined);

    await projectApi.removeMember("proj-1", "user-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/members/user-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("projectApi.startWriting", () => {
  test("POSTs to start-writing and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      thread_id: "thread-abc",
      project_id: "proj-1",
    });

    const result = await projectApi.startWriting("proj-1");
    expect(result.threadId).toBe("thread-abc");
    expect(result.projectId).toBe("proj-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/start-writing",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("projectApi.startChapterEditing", () => {
  test("POSTs to start-editing and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      thread_id: "thread-xyz",
      project_id: "proj-1",
      chapter_id: "ch-2",
    });

    const result = await projectApi.startChapterEditing("proj-1", "ch-2");
    expect(result.threadId).toBe("thread-xyz");
    expect(result.chapterId).toBe("ch-2");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/chapters/ch-2/start-editing",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
