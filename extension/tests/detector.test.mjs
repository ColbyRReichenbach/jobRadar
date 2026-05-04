import assert from "node:assert/strict";
import test from "node:test";

import { detectPlatform } from "../detector.js";

test("detects supported ATS URLs", () => {
  assert.equal(detectPlatform("https://boards.greenhouse.io/acme/jobs/123")?.platform, "greenhouse");
  assert.equal(detectPlatform("https://jobs.lever.co/acme/abc")?.platform, "lever");
  assert.equal(detectPlatform("https://jobs.ashbyhq.com/acme/abc")?.platform, "ashby");
  assert.equal(detectPlatform("https://company.wd5.myworkdayjobs.com/en-US/site/job/title_JR123")?.platform, "workday");
});

test("keeps broad job boards detectable for manual side-panel flows", () => {
  assert.equal(detectPlatform("https://www.linkedin.com/jobs/view/123")?.platform, "linkedin");
  assert.equal(detectPlatform("https://www.indeed.com/viewjob?jk=abc")?.platform, "indeed");
  assert.equal(detectPlatform("https://www.glassdoor.com/job-listing/example")?.platform, "glassdoor");
});
