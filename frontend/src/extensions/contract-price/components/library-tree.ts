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
  for (const f of [...folders].sort((a, b) =>
    a.name.localeCompare(b.name, "zh-Hans-CN"),
  )) {
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
  // EAI-CUSTOM: 深度帽 64——历史脏数据 parent 链成环时防浏览器挂死（质量审查 Task 8）。
  let depth = 0;
  while (cur && depth < 64) {
    chain.unshift({ id: cur.id, name: cur.name });
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
    depth += 1;
  }
  // 截断（成环/超深未触根）视同未知 id：丢弃 chain，优雅返回 [虚拟根] 单节。
  if (cur) return [{ id: ROOT_ID, name: "文件库" }];
  return [{ id: ROOT_ID, name: "文件库" }, ...chain];
}
