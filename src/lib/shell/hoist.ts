// `use:hoist={target}`: the element lives in `target` instead of where it's
// written. A panel's status section is moved this way into the slot its
// host keeps for it in the status bar (PANELS.md); it keeps its component's
// state and handlers, and only its place in the document changes.

export function hoist(node: HTMLElement, target: HTMLElement) {
  target.appendChild(node);
  return {
    update(next: HTMLElement) {
      if (node.parentNode !== next) next.appendChild(node);
    },
    destroy() {
      node.remove();
    },
  };
}
