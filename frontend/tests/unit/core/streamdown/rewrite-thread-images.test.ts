import {
  afterEach,
  beforeEach,
  describe,
  expect,
  test,
  rs,
} from "@rstest/core";

// EAI-CUSTOM: regression tests for rewriteThreadImageReferences — thread
// reports embed images as relative `images/<name>.<ext>` refs that only
// resolve through the owning thread's artifact API.

const ENV_KEYS = [
  "NEXT_PUBLIC_BACKEND_BASE_URL",
  "NEXT_PUBLIC_STATIC_WEBSITE_ONLY",
] as const;

type EnvSnapshot = Partial<
  Record<(typeof ENV_KEYS)[number], string | undefined>
>;

function snapshotEnv(): EnvSnapshot {
  const snapshot: EnvSnapshot = {};
  for (const key of ENV_KEYS) {
    snapshot[key] = process.env[key];
  }
  return snapshot;
}

function setEnv(key: (typeof ENV_KEYS)[number], value: string | undefined) {
  const env = process.env as Record<string, string | undefined>;
  if (value === undefined) {
    delete env[key];
  } else {
    env[key] = value;
  }
}

function restoreEnv(snapshot: EnvSnapshot) {
  for (const key of ENV_KEYS) {
    setEnv(key, snapshot[key]);
  }
}

function markdownImage(url: string) {
  return `![a](${url})`;
}

async function loadFreshPreprocess() {
  rs.resetModules();
  return await import("@/core/streamdown/preprocess");
}

describe("rewriteThreadImageReferences", () => {
  let saved: EnvSnapshot;

  beforeEach(() => {
    saved = snapshotEnv();
    setEnv("NEXT_PUBLIC_BACKEND_BASE_URL", undefined);
    setEnv("NEXT_PUBLIC_STATIC_WEBSITE_ONLY", undefined);
  });

  afterEach(() => {
    restoreEnv(saved);
  });

  test("rewrites relative markdown image refs to the owning thread's artifact URLs", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();

    expect(
      rewriteThreadImageReferences(
        "![滤网起吊示意图](images/08bb824f44bb.png)",
        "thread-1",
      ),
    ).toBe(
      "![滤网起吊示意图](/api/threads/thread-1/artifacts/mnt/user-data/outputs/images/08bb824f44bb.png)",
    );
  });

  test("rewrites every relative ref on a line, honoring ./ prefixes and titles", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();
    const artifactBase = (threadId: string, name: string) =>
      `/api/threads/${threadId}/artifacts/mnt/user-data/outputs/images/${name}`;

    expect(
      rewriteThreadImageReferences(
        `![泵房剖面](./images/7f8g.png "示意图") 文本 ![吸水口](images/9a2b.jpeg)`,
        "t",
      ),
    ).toBe(
      `![泵房剖面](${artifactBase("t", "7f8g.png")} "示意图") 文本 ![吸水口](${artifactBase("t", "9a2b.jpeg")})`,
    );
  });

  test("preserves query and fragment suffixes on rewritten refs", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();

    expect(
      rewriteThreadImageReferences(markdownImage("images/x.png?v=2#fig"), "t"),
    ).toBe(
      markdownImage(
        "/api/threads/t/artifacts/mnt/user-data/outputs/images/x.png?v=2#fig",
      ),
    );
  });

  test("leaves absolute, root-relative, data, and non-image refs untouched", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();
    const markdown = [
      "![web](https://example.com/images/x.png)",
      "![root](/images/x.png)",
      "![data](data:image/png;base64,AAAA)",
      "![text](images/notes.txt)",
      "![subdir](static/images/x.png)",
    ].join("\n");

    expect(rewriteThreadImageReferences(markdown, "t")).toBe(markdown);
  });

  test("rewrites raw HTML img srcs but not srcset or external sources", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();

    expect(
      rewriteThreadImageReferences(
        '<p><img src="images/x.png" alt="a"></p>',
        "t",
      ),
    ).toBe(
      '<p><img src="/api/threads/t/artifacts/mnt/user-data/outputs/images/x.png" alt="a"></p>',
    );
    expect(
      rewriteThreadImageReferences(
        '<img src="https://example.com/images/x.png" srcset="images/x.png 2x">',
        "t",
      ),
    ).toBe(
      '<img src="https://example.com/images/x.png" srcset="images/x.png 2x">',
    );
  });

  test("leaves refs inside fenced and indented code blocks untouched", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();
    const fenced = "```text\n![a](images/x.png)\n```";
    const indented = "    ![a](images/x.png)";

    expect(rewriteThreadImageReferences(fenced, "t")).toBe(fenced);
    expect(rewriteThreadImageReferences(indented, "t")).toBe(indented);
  });

  test("keeps prose around rewritten refs intact across mixed lines", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();
    const markdown =
      "# 计算书\n\n正文段落。\n\n![图](images/08bb824f44bb.png)\n\n结束。";

    expect(rewriteThreadImageReferences(markdown, "t")).toBe(
      "# 计算书\n\n正文段落。\n\n![图](/api/threads/t/artifacts/mnt/user-data/outputs/images/08bb824f44bb.png)\n\n结束。",
    );
  });

  test("targets the mock artifact API for mock threads", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();

    expect(
      rewriteThreadImageReferences(markdownImage("images/x.png"), "t", true),
    ).toBe(
      markdownImage(
        "/mock/api/threads/t/artifacts/mnt/user-data/outputs/images/x.png",
      ),
    );
  });

  test("honors an explicit backend base URL", async () => {
    setEnv("NEXT_PUBLIC_BACKEND_BASE_URL", "http://backend:8001");
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();

    expect(
      rewriteThreadImageReferences(markdownImage("images/x.png"), "t"),
    ).toBe(
      markdownImage(
        "http://backend:8001/api/threads/t/artifacts/mnt/user-data/outputs/images/x.png",
      ),
    );
  });

  test("returns markdown without image refs unchanged", async () => {
    const { rewriteThreadImageReferences } = await loadFreshPreprocess();
    const markdown = "# 标题\n\n普通正文，无图片。\n";

    expect(rewriteThreadImageReferences(markdown, "t")).toBe(markdown);
  });
});
