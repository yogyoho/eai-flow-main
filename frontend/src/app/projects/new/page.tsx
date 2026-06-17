import { Suspense } from "react";

import { ProjectCreateWizard } from "@/extensions/project/ProjectCreateWizard";
import { ShellLayout } from "@/extensions/shell/ShellLayout";

export default function NewProjectPage() {
  return (
    <ShellLayout>
      <Suspense>
        <ProjectCreateWizard />
      </Suspense>
    </ShellLayout>
  );
}
