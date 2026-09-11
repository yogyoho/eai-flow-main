"use client";

// EAI-CUSTOM (Plan 4): 投标资料管理主组件——资质版本库 + 标书样例台账双 tab。
// 镜像 eia-samples/SampleLibrary.tsx 的 tab 形态(Tabs+TabsContent, Shadcn)。
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { QualificationLibrary } from "./QualificationLibrary";
import { SampleLibrary } from "./SampleLibrary";

export default function BidMaterials() {
  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col gap-4 p-4">
      <div>
        <h1 className="text-lg font-semibold">投标资料管理</h1>
        <p className="text-sm text-muted-foreground">
          投标资质版本库（MinIO 代理、到期预警）与标书技术资料台账（bank_compile 样例）。
        </p>
      </div>
      <Tabs defaultValue="qualifications" className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="qualifications">资质库</TabsTrigger>
          <TabsTrigger value="samples">样例库</TabsTrigger>
        </TabsList>
        <TabsContent value="qualifications" className="min-h-0 flex-1">
          <QualificationLibrary />
        </TabsContent>
        <TabsContent value="samples" className="min-h-0 flex-1">
          <SampleLibrary />
        </TabsContent>
      </Tabs>
    </div>
  );
}
