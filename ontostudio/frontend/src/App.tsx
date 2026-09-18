/**
 * OntoStudio standalone frontend app shell (S2 Task 1, EAI-CUSTOM).
 * 单页挂本体三视图工作台（地图|概览|实体消解），无路由。
 */
import { OntologyPage } from "@/components/OntologyPage";

export function App() {
  return (
    <div className="h-dvh w-full overflow-hidden">
      <OntologyPage />
    </div>
  );
}
