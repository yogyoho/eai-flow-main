/**
 * OntoStudio standalone frontend app shell (S2 Task 1 → 9-page skeleton, EAI-CUSTOM).
 * AppShell 侧栏 + hash 路由：知识层三视图（OntologyPage 真实功能）+ 六骨架页。
 */
import { AppShell } from "@/layout/AppShell";

export function App() {
  return (
    <div className="h-dvh w-full overflow-hidden">
      <AppShell />
    </div>
  );
}
