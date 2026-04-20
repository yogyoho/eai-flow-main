/**
 * sectionHighlighter.ts
 * Highlights a section briefly when navigated to
 */

const HIGHLIGHT_DURATION = 2000;

export function highlightSection(element: HTMLElement, duration = HIGHLIGHT_DURATION) {
  const originalBg = element.style.backgroundColor;
  const originalTransition = element.style.transition;
  element.style.transition = "background-color 0.3s ease";
  element.style.backgroundColor = "rgba(79, 70, 229, 0.15)";
  setTimeout(() => {
    element.style.backgroundColor = originalBg;
    setTimeout(() => {
      element.style.transition = originalTransition;
    }, 300);
  }, duration);
}
