# AI Assistant Panel Refactor Design

**Date**: 2026-05-20
**File**: `frontend/src/extensions/docmgr/DocumentManagement.tsx`
**Scope**: Refactor `AIEditPanel` component — minimal layout change, internal UI overhaul

## Goal

Replace the current single-shot operation card UI with a multi-turn conversational AI chat panel (right sidebar, 360px). The panel layout (editor + animated sidebar) stays the same; only the panel internals change.

## Current State

- `AIEditPanel` is a 320px animated sidebar (Framer Motion)
- 4 operation cards (润色/扩写/缩写/头脑风暴), each with icon + description
- Model selector dropdown in content area
- Single "执行" button triggers `docmgrApi.aiEdit()`, returns plain text
- Result displayed as `whitespace-pre-wrap` text with one "替换选中内容" button at footer

## Target State

Compact, chat-based interface following the approved mockup (右侧面板方案):

```
┌─────────────────────────┐
│ ✨ AI 助手        🔄 ✕  │  Header
├─────────────────────────┤
│ [润色] [扩写] [缩写]    │  Quick action pills (always visible)
│ [头脑风暴]              │
├─────────────────────────┤
│                         │
│  (empty state or        │  Message area (flex-1, scrollable)
│   conversation history) │
│                         │
├─────────────────────────┤
│ [GPT-4o ▾ | input... ▶]│  Bottom input bar (inline model selector)
└─────────────────────────┘
```

## Changes

### 1. Layout: 320px → 360px

One-line change in `DocumentEditor`: `width: 320` → `width: 360`.

### 2. State: Single result → Conversation history

Replace:

```tsx
const [result, setResult] = useState("");
const [error, setError] = useState("");
```

With:

```tsx
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  operation?: AIOperation; // attached for user messages from quick actions
}
const [messages, setMessages] = useState<ChatMessage[]>([]);
const [input, setInput] = useState("");
```

No persistence — `useState` only, clears on unmount or "新对话" button.

### 3. Quick action pills replace operation cards

Current: 4 tall cards with icon + description (~200px total height).

New: Single row of compact pill buttons (~32px height). Selected pill appends operation context to the message. Pills remain visible at all times (above message area).

```
[润色] [扩写] [缩写] [头脑风暴]
```

Selected state: filled background (primary color). Unselected: outline border.

### 4. Bottom input bar with inline model selector

Current: Model dropdown in content area + "执行" button in footer.

New: Single-row input bar fixed at bottom:

```
┌──────────────────────────────────────┐
│ [默认模型 ▾] | [type here...    ] [▶]│
└──────────────────────────────────────┘
```

- Model selector: compact `<select>` inline with input, separator `|`
- Send button: round (▶), primary color
- Quick actions: clicking a pill auto-sends (if text selected) or sets operation context

### 5. Message area with Markdown rendering

Empty state (no messages):

```
💬
AI 文档助手
在编辑器中选中文字，选择操作后发送
或在下方直接输入自定义指令

📌 请阅读全文并总结要点
📝 帮我优化文档结构
```

Conversation state:
- User messages: right-aligned, primary color bubble, shows operation tag if from quick action
- AI responses: left-aligned, light background, rendered with `react-markdown` (already installed)
- Each AI response has "替换" and "复制" action buttons below

### 6. API interaction (no backend change)

Each user message triggers `docmgrApi.aiEdit()` with:
- `text`: selected text from editor (if any), otherwise the input text
- `operation`: selected quick action (defaults to "polish")
- `model_name`: from inline selector

For multi-turn context, the frontend sends the full conversation history as part of the text payload (prepended as context), or we add a new optional `history` field to the API. **Initial implementation: keep single-shot API, just improve the UI.** Multi-turn context can be added later.

The response is appended as an assistant message. Streaming is not in scope for this iteration.

### 7. Action buttons per response

- **替换**: Calls `onResult(message.content)` — replaces editor selection with AI response
- **复制**: `navigator.clipboard.writeText(message.content)` with sonner toast

## Component Structure

```
AIEditPanel (refactored)
├── Header: title + new-conversation button + close button
├── QuickActionPills: compact row of operation pills
├── MessageArea (flex-1, scrollable)
│   ├── EmptyState (when messages.length === 0)
│   └── MessageList
│       ├── UserMessage (right-aligned bubble)
│       └── AssistantMessage (left-aligned, markdown rendered)
│           └── ActionButtons (replace + copy)
└── InputBar (fixed bottom)
    ├── ModelSelector (inline <select>)
    ├── TextInput
    └── SendButton (round)
```

All within the existing `AIEditPanel` component in `DocumentManagement.tsx`. No new files needed — the panel is self-contained.

## Imports to Add

- `react-markdown` (already in package.json)
- `remark-gfm` (already in package.json)
- `Send` icon from `lucide-react` (for round send button)

## Not in Scope

- Streaming responses (use existing single-shot API)
- Conversation persistence across sessions
- Backend API changes
- File upload in chat
- Custom system prompts
