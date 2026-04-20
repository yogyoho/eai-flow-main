/**
 * scrollHelper.ts
 * Scroll utilities for the editor
 */

export function getRelativePosition(el: HTMLElement, container: HTMLElement) {
  const elRect = el.getBoundingClientRect();
  const containerRect = container.getBoundingClientRect();
  return {
    relativeTop: elRect.top - containerRect.top + container.scrollTop,
    relativeBottom: elRect.bottom - containerRect.top + container.scrollTop,
  };
}

export function scrollToElement(element: HTMLElement, offsetTop = 80) {
  const elRect = element.getBoundingClientRect();
  const scrollTop = window.scrollY + elRect.top - offsetTop;
  window.scrollTo({ top: scrollTop, behavior: "smooth" });
}
