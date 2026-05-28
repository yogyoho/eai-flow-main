import { expect, test, describe, vi, beforeEach } from "vitest";

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
      { id: "p1", name: "Test", report_type: "other", status: "active", chapter_count: 3, member_count: 2, template_name: "环评模板" },
    ];
    mockFetch.mockResolvedValueOnce({ items, total: 1 });

    const result = await projectApi.list();
    expect(result.total).toBe(1);
    expect(result.items[0]!.reportType).toBe("other");
    expect(result.items[0]!.chapterCount).toBe(3);
    expect(result.items[0]!.templateName).toBe("环评模板");
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("/projects?"));
  });

  test("passes filter params as query string", async () => {
    mockFetch.mockResolvedValueOnce({ items: [], total: 0 });

    await projectApi.list({ status: "active", reportType: "environmental_impact", search: "test", skip: 5, limit: 10 });

    const url = mockFetch.mock.calls[0]![0] as string;
    expect(url).toContain("status=active");
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
      status: "active",
      created_at: "2024-01-01",
    });

    const result = await projectApi.get(pid);
    expect(result.id).toBe(pid);
    expect(result.reportType).toBe("other");
    expect(result.status).toBe("active");
    expect(mockFetch).toHaveBeenCalledWith(`/project/projects/${pid}`);
  });
});

describe("projectApi.create", () => {
  test("POSTs with snake_case body and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      id: "new-1",
      name: "New Project",
      report_type: "environmental_impact",
      status: "active",
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

describe("projectApi.enter", () => {
  test("POSTs to enter and returns camelCase", async () => {
    mockFetch.mockResolvedValueOnce({
      thread_id: "thread-abc",
      project_id: "proj-1",
    });

    const result = await projectApi.enter("proj-1");
    expect(result.threadId).toBe("thread-abc");
    expect(result.projectId).toBe("proj-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/project/projects/proj-1/enter",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("projectApi.getFiles", () => {
  test("fetches project files", async () => {
    const files = [
      { name: "report.docx", thread_id: "t1", size: 1024 },
    ];
    mockFetch.mockResolvedValueOnce(files);

    const result = await projectApi.getFiles("proj-1");
    expect(result).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith("/project/projects/proj-1/files");
  });
});

describe("projectApi.addMember", () => {
  test("POSTs member with snake_case body", async () => {
    mockFetch.mockResolvedValueOnce(undefined);

    await projectApi.addMember("proj-1", "user-1", "member");
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
