/**
 * EAI-CUSTOM cpa v3: 合同文件库文件夹树纯函数（镜像翻译资产库的虚拟根语义）。
 * buildFolderTree: 扁平 tlt_folders 式列表 → 树（中文排序）。
 * pathOf: 节点 → 面包屑路径链（首节为虚拟根「文件库」）。
 */

export interface LibraryFolderLike {
  id: string;
  parent_id: string | null;
  name: string;
}

export interface FolderNode extends LibraryFolderLike {
  children: FolderNode[];
}

export const ROOT_ID = "root";

export function buildFolderTree(folders: LibraryFolderLike[]): FolderNode[] {
  const byParent = new Map<string | null, FolderNode[]>();
  for (const f of [...folders].sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"))) {
    const node: FolderNode = { ...f, children: [] };
    const key = f.parent_id ?? null;
    const list = byParent.get(key) ?? [];
    list.push(node);
    byParent.set(key, list);
  }
  const attach = (parentId: string | null): FolderNode[] => {
    const nodes = byParent.get(parentId) ?? [];
    for (const n of nodes) n.children = attach(n.id);
    return nodes;
  };
  return attach(null);
}

export function pathOf(
  folders: LibraryFolderLike[],
  id: string,
): { id: string; name: string }[] {
  if (id === ROOT_ID) return [{ id: ROOT_ID, name: "文件库" }];
  const byId = new Map(folders.map((f) => [f.id, f]));
  const chain: { id: string; name: string }[] = [];
  let cur = byId.get(id);
  while (cur) {
    chain.unshift({ id: cur.id, name: cur.name });
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return [{ id: ROOT_ID, name: "文件库" }, ...chain];
}
