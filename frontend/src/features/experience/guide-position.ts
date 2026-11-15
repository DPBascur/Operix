export type FocusRect = {
  top: number;
  left: number;
  width: number;
  height: number;
  radius: number;
};

export function positionGuide(
  rect: FocusRect,
  width: number,
  height: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const margin = 12;
  const gap = 16;
  const right = rect.left + rect.width;
  const bottom = rect.top + rect.height;
  const clamp = (value: number, end: number) =>
    Math.max(margin, Math.min(value, end));
  const left = clamp(rect.left, viewportWidth - width - margin);
  const top = clamp(
    rect.top + (rect.height - height) / 2,
    viewportHeight - height - margin,
  );

  if (viewportWidth >= 680 && right + gap + width <= viewportWidth - margin)
    return { left: right + gap, top };
  if (viewportWidth >= 680 && rect.left - gap - width >= margin)
    return { left: rect.left - gap - width, top };
  if (bottom + gap + height <= viewportHeight - margin)
    return { left, top: bottom + gap };
  if (rect.top - gap - height >= margin)
    return { left, top: rect.top - gap - height };
  return null;
}

export function visibleControl(selector: string) {
  for (const candidate of selector.split(",")) {
    const element = [...document.querySelectorAll<HTMLElement>(candidate)].find(
      (node) =>
        node.getClientRects().length &&
        !node.matches(":disabled") &&
        !node.closest("[inert], [hidden]") &&
        getComputedStyle(node).visibility === "visible",
    );
    if (element) return element;
  }
  return null;
}

export function focusRect(element: HTMLElement): FocusRect | null {
  const rect = element.getBoundingClientRect();
  const margin = 5;
  let left = Math.max(0, rect.left - margin);
  let top = Math.max(0, rect.top - margin);
  let right = Math.min(
    document.documentElement.clientWidth,
    rect.right + margin,
  );
  let bottom = Math.min(window.innerHeight, rect.bottom + margin);

  for (
    let parent = element.parentElement;
    parent && parent !== document.body;
    parent = parent.parentElement
  ) {
    const { overflowX, overflowY } = getComputedStyle(parent);
    const clips = /auto|scroll|hidden|clip/;
    if (!clips.test(overflowX) && !clips.test(overflowY)) continue;
    const bounds = parent.getBoundingClientRect();
    if (clips.test(overflowX)) {
      left = Math.max(left, bounds.left);
      right = Math.min(right, bounds.right);
    }
    if (clips.test(overflowY)) {
      top = Math.max(top, bounds.top);
      bottom = Math.min(bottom, bounds.bottom);
    }
  }
  const header = document.querySelector(".app-header")?.getBoundingClientRect();
  if (header && !element.closest(".app-header"))
    top = Math.max(top, header.bottom);
  if (right <= left || bottom <= top) return null;
  return {
    left,
    top,
    width: right - left,
    height: bottom - top,
    radius: Math.min(
      (bottom - top) / 2,
      (parseFloat(getComputedStyle(element).borderTopLeftRadius) || 4) + margin,
    ),
  };
}
