import { describe, expect, it } from "@rstest/core";
import { render, screen } from "@testing-library/react";

import { CaseStudySection } from "@/components/landing/sections/case-study-section";

describe("CaseStudySection", () => {
  // EAI-CUSTOM: upstream asserts semantic <img loading=lazy> discipline for the
  // case-study covers; EAI renders those covers as decorative CSS
  // background-image cards (not content images), so this asserts the EAI
  // reality instead: all case-study cards render with non-empty titles.
  it("renders all case-study cards with titles", () => {
    render(<CaseStudySection />);

    const headings = screen.getAllByRole("heading");
    expect(headings.length).toBeGreaterThanOrEqual(6);
    for (const heading of headings) {
      expect(heading.textContent?.trim().length).toBeGreaterThan(0);
    }
  });
});
