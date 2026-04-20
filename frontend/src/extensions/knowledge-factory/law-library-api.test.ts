import assert from "node:assert/strict";
import test from "node:test";

const originalKfApiBaseUrl = process.env.NEXT_PUBLIC_KF_API_BASE_URL;

void test("buildLawLibraryUrl does not duplicate /api when base already contains it", async () => {
  process.env.NEXT_PUBLIC_KF_API_BASE_URL = "http://localhost:4026/api";

  const { buildLawLibraryUrl } = await import(
    new URL("./law-library-api.ts", import.meta.url).href
  );

  assert.equal(
    buildLawLibraryUrl("/kf/laws/parse-file"),
    "http://localhost:4026/api/kf/laws/parse-file"
  );
});

void test("buildLawLibraryUrl appends query params once", async () => {
  process.env.NEXT_PUBLIC_KF_API_BASE_URL = "http://localhost:4026/api/";

  const { buildLawLibraryUrl } = await import(
    new URL("./law-library-api.ts", import.meta.url).href
  );

  assert.equal(
    buildLawLibraryUrl("/kf/laws", { page: 2, law_type: "technical" }),
    "http://localhost:4026/api/kf/laws?page=2&law_type=technical"
  );
});

test.after(() => {
  if (originalKfApiBaseUrl === undefined) {
    delete process.env.NEXT_PUBLIC_KF_API_BASE_URL;
    return;
  }

  process.env.NEXT_PUBLIC_KF_API_BASE_URL = originalKfApiBaseUrl;
});
