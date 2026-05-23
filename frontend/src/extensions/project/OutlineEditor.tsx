"use client";

import { ChevronDown, ChevronRight, GripVertical, Plus, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { ChapterTreeNode } from "./types";

interface OutlineEditorProps {
  chapters: ChapterTreeNode[];
  onChange: (chapters: ChapterTreeNode[]) => void;
  readOnly?: boolean;
}

function getAtPath(nodes: ChapterTreeNode[], path: number[]): ChapterTreeNode | null {
  let current = nodes;
  let node: ChapterTreeNode | null = null;
  for (const idx of path) {
    if (idx >= current.length) return null;
    node = current[idx] ?? null;
    if (!node) return null;
    current = node.children;
  }
  return node;
}

function setAtPath(
  nodes: ChapterTreeNode[],
  path: number[],
  updater: (node: ChapterTreeNode) => ChapterTreeNode,
): ChapterTreeNode[] {
  if (path.length === 0) return nodes;
  const [head, ...rest] = path;
  return nodes.map((node, i) => {
    if (i !== head) return node;
    if (rest.length === 0) return updater(node);
    return { ...node, children: setAtPath(node.children, rest, updater) };
  });
}

function removeAtPath(nodes: ChapterTreeNode[], path: number[]): ChapterTreeNode[] {
  if (path.length === 0) return nodes;
  const [head, ...rest] = path;
  if (rest.length === 0) {
    return nodes.filter((_, i) => i !== head);
  }
  return nodes.map((node, i) => {
    if (i !== head) return node;
    return { ...node, children: removeAtPath(node.children, rest) };
  });
}

function OutlineNodeRow({
  node,
  path,
  onChange,
  onRemove,
  onAddChild,
  readOnly,
}: {
  node: ChapterTreeNode;
  path: number[];
  onChange: (path: number[], node: ChapterTreeNode) => void;
  onRemove: (path: number[]) => void;
  onAddChild: (path: number[]) => void;
  readOnly: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-muted/50 group",
          node.level === 1 && "font-medium",
        )}
        style={{ paddingLeft: `${(node.level - 1) * 24 + 8}px` }}
      >
        {!readOnly && (
          <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab shrink-0" />
        )}

        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}

        {readOnly ? (
          <span className="text-sm text-foreground truncate flex-1">{node.title}</span>
        ) : (
          <Input
            value={node.title}
            onChange={(e) => onChange(path, { ...node, title: e.target.value })}
            className="h-7 text-sm border-transparent hover:border-border focus:border-primary flex-1"
          />
        )}

        {!readOnly && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => onAddChild(path)}
            >
              <Plus className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={() => onRemove(path)}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      {expanded && hasChildren && (
        <div>
          {node.children.map((child, childIndex) => (
            <OutlineNodeRow
              key={`${child.title}-${childIndex}`}
              node={child}
              path={[...path, childIndex]}
              onChange={onChange}
              onRemove={onRemove}
              onAddChild={onAddChild}
              readOnly={readOnly}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function OutlineEditor({ chapters, onChange, readOnly = false }: OutlineEditorProps) {
  const handleChange = useCallback(
    (path: number[], updated: ChapterTreeNode) => {
      onChange(setAtPath(chapters, path, () => updated));
    },
    [chapters, onChange],
  );

  const handleRemove = useCallback(
    (path: number[]) => {
      onChange(removeAtPath(chapters, path));
    },
    [chapters, onChange],
  );

  const handleAddChild = useCallback(
    (path: number[]) => {
      const newChild: ChapterTreeNode = {
        title: "新章节",
        level: path.length + 2,
        sortOrder: 0,
        children: [],
      };
      onChange(
        setAtPath(chapters, path, (node) => ({
          ...node,
          children: [...node.children, newChild],
        })),
      );
    },
    [chapters, onChange],
  );

  const handleAddRoot = useCallback(() => {
    const newNode: ChapterTreeNode = {
      title: "新章节",
      level: 1,
      sortOrder: chapters.length,
      children: [],
    };
    onChange([...chapters, newNode]);
  }, [chapters, onChange]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-medium text-foreground">
          {readOnly ? "大纲预览" : "编辑大纲"}
        </h3>
        {!readOnly && (
          <Button variant="outline" size="sm" className="gap-1" onClick={handleAddRoot}>
            <Plus className="h-3 w-3" />
            添加章节
          </Button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {chapters.length === 0 ? (
          <div className="text-center text-sm text-muted-foreground py-8">
            暂无章节，点击"添加章节"开始
          </div>
        ) : (
          chapters.map((node, index) => (
            <OutlineNodeRow
              key={`${node.title}-${index}`}
              node={node}
              path={[index]}
              onChange={handleChange}
              onRemove={handleRemove}
              onAddChild={handleAddChild}
              readOnly={readOnly}
            />
          ))
        )}
      </div>
    </div>
  );
}
