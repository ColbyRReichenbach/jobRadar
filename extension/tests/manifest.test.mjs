import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const manifest = JSON.parse(
  await readFile(new URL("../manifest.json", import.meta.url), "utf8")
);

const highRiskHosts = ["linkedin.com", "indeed.com", "glassdoor.com"];

test("manifest does not auto-inject extraction scripts on high-risk job boards", () => {
  const extractionScripts = manifest.content_scripts.find((entry) =>
    entry.js.includes("content.js")
  );
  assert.ok(extractionScripts, "expected extraction content script entry");
  for (const match of extractionScripts.matches) {
    assert.equal(
      highRiskHosts.some((host) => match.includes(host)),
      false,
      `${match} should not auto-inject extraction scripts`
    );
  }
});

test("manifest does not request high-risk job-board host permissions", () => {
  for (const permission of manifest.optional_host_permissions || []) {
    assert.equal(
      highRiskHosts.some((host) => permission.includes(host)),
      false,
      `${permission} should not be requested as a host permission`
    );
  }
});

test("manifest keeps extension scripts under local CSP", () => {
  assert.equal(
    manifest.content_security_policy.extension_pages,
    "script-src 'self'; object-src 'self'"
  );
});

test("local development hosts are not content script targets", () => {
  const contentMatches = manifest.content_scripts.flatMap((entry) => entry.matches || []);
  for (const match of contentMatches) {
    assert.equal(
      match.startsWith("http://localhost") || match.startsWith("http://127.0.0.1"),
      false,
      `${match} should not auto-inject on local development hosts`
    );
  }
});
