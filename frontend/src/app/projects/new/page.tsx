import { Suspense } from "react";
import { ShellLayout } from "@/extensions/shell/ShellLayout";
import { ProjectCreateWizard } from "@/extensions/project/ProjectCreateWizard";

export default function NewProjectPage() {
  return (
    <ShellLayout>
      <Suspense>
        <ProjectCreateWizard />
      </Suspense>
    </ShellLayout>
  );
}
