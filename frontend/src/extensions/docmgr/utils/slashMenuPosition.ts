export interface SlashMenuAnchorPosition {
  top: number;
  left: number;
}

export interface SlashMenuSize {
  width: number;
  height: number;
}

const VIEWPORT_PADDING = 12;
const MENU_GAP = 8;

export function getSlashMenuViewportPosition(
  anchor: SlashMenuAnchorPosition,
  menuSize: SlashMenuSize,
  viewport: { width: number; height: number }
): SlashMenuAnchorPosition {
  const maxLeft = Math.max(VIEWPORT_PADDING, viewport.width - menuSize.width - VIEWPORT_PADDING);
  const maxTop = Math.max(VIEWPORT_PADDING, viewport.height - menuSize.height - VIEWPORT_PADDING);

  let left = Math.min(Math.max(anchor.left, VIEWPORT_PADDING), maxLeft);
  let top = anchor.top;

  if (top + menuSize.height > viewport.height - VIEWPORT_PADDING) {
    top = Math.max(VIEWPORT_PADDING, anchor.top - menuSize.height - MENU_GAP * 2);
  }

  top = Math.min(Math.max(top, VIEWPORT_PADDING), maxTop);
  left = Math.min(Math.max(left, VIEWPORT_PADDING), maxLeft);

  return { top, left };
}
