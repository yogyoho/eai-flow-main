---
name: report-write
description: AI驱动的报告章节撰写和协作编辑策略。当对话线程包含项目上下文（project_id）时激活，引导Agent通过Project MCP工具完成章节撰写和编辑任务。
---

# Report Writing Skill

## Trigger

Activate this skill when the thread metadata contains a `project_id` key. The metadata type determines the mode:

- `type: "report_project"` → Stage 3: Full AI writing mode
- `type: "chapter_edit"` → Stage 4: Collaborative editing mode

## Stage 3: AI Writing Mode

When the user starts AI writing for a project, follow this workflow:

### Step 1: Understand the project

```
get_project(project_id) → project name, type, stage
list_chapters(project_id) → all chapters with status
```

### Step 2: Write chapters sequentially

For each chapter with status "pending":

```
get_chapter_spec(chapter_id) → full writing specification
```

Key fields in the spec:
- **purpose**: What this chapter should cover — read this first
- **content_contract**: Structure constraints
  - **key_elements**: Must cover ALL of these
  - **structure_type**: "narrative_text", "data_table", etc.
  - **style_rules**: Writing style to follow
  - **min_word_count**: Minimum acceptable length
  - **forbidden_phrases**: Never use these expressions
- **generation_hint**: Additional writing guidance
- **rag_sources**: Knowledge bases to query for reference material
- **example_snippet**: Reference structure (do NOT copy verbatim)
- **compliance_rules**: Regulations/standards the content must satisfy
- **neighbors**: Previous/next chapter titles and summaries for continuity

### Step 3: Generate and write

1. If `rag_sources` exists, query the referenced knowledge bases for supporting data
2. Generate content following the spec precisely:
   - Cover ALL `key_elements`
   - Respect `min_word_count` as the floor, `word_count_target` as the target
   - Follow `style_rules` exactly
   - NEVER use phrases from `forbidden_phrases`
   - Reference `example_snippet` for structure only, not content
   - Ensure continuity with neighbor chapters (consistent terminology, logical flow)
3. Write the result:
   ```
   write_chapter(chapter_id, content, "draft")
   ```

### Step 4: Continue to next chapter

Repeat Step 2-3 for the next pending chapter. Inform the user of progress after each chapter.

### User intervention

If the user provides direction (e.g., "focus on water quality in chapter 3"), adjust the writing accordingly. User instructions override the default spec for that chapter.

## Stage 4: Collaborative Editing Mode

In this mode, the user drives the interaction. You assist on demand.

**Rules:**
- Respond to user requests; do NOT proactively write chapters
- When editing content, write back with `status: "editing"`
- Available operations:
  - Read chapter: `read_chapter(chapter_id)`
  - Write chapter: `write_chapter(chapter_id, content, "editing")`
  - View full spec: `get_chapter_spec(chapter_id)`
  - See all chapters: `list_chapters(project_id)`

Common requests:
- "Polish this paragraph" → Read, improve writing quality, write back
- "Add data analysis for section X" → Read, research via RAG, add content, write back
- "Check consistency with chapter Y" → Read both, compare terminology/flow, suggest edits
- "Expand section Z to meet word count" → Read, identify thin sections, expand, write back

## Writing Quality Standards

- Use formal, professional Chinese appropriate for technical reports
- Cite data sources: 标注数据来源 (e.g., "根据XX监测数据...")
- Maintain consistent terminology across chapters
- Use parallel structure in headings at the same level
- Avoid filler words: "的" overuse, "进行了" → use direct verbs
- Each paragraph should have a clear topic sentence
