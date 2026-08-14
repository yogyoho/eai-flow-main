// EAI-CUSTOM: the EAI landing page is landing-new (a fork-specific rewrite), not
// the upstream landing/ sections. Restored 2026-08-15 after the upstream sync
// overwrote page.tsx to point at landing/*.
import LandingNew from "@/components/landing-new";

export default function LandingPage() {
  return <LandingNew />;
}
