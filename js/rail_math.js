// railPages and railPage: how a scrolling strip is cut into pages.
//
// This module is the single definition, loaded by js/film.js at runtime and
// required by tools/rail_math.mjs, so the test exercises the code the browser
// runs rather than a copy of it.
//
// Pages are counted from the distance left to scroll, NOT from
// scrollWidth / clientWidth: that ratio rounds the tail away. A track 849px wide
// showing 1080px of cards has 231px still hidden -- a real second page -- but
// round(1080 / 849) is 1, and the next arrow ends up disabled with a fifth of
// the strip unreachable.

function railPages(clientWidth, scrollWidth) {
  const maxScroll = scrollWidth - clientWidth;
  if (maxScroll <= 1) return 1;
  const page = clientWidth - 1;
  if (page <= 0) return 1;
  return Math.ceil(maxScroll / page) + 1;
}

function railPage(scrollLeft, clientWidth, scrollWidth, pages) {
  const page = clientWidth - 1;
  if (page <= 0 || pages <= 1) return 0;
  // Sitting at the very end is the last page, not round(maxScroll / page).
  // The browser clamps scrollLeft to scrollWidth - clientWidth, and on a short
  // last page that is nowhere near (pages - 1) * pageWidth: a strip 849px wide
  // with 231px left to scroll ends at 231, which the plain ratio reads as page 0.
  // Without this the "previous" arrow stays disabled at the end of the strip.
  const maxScroll = scrollWidth - clientWidth;
  if (maxScroll > 1 && scrollLeft >= maxScroll - 2) return pages - 1;
  return Math.min(pages - 1, Math.max(0, Math.round(scrollLeft / page)));
}

function railScrollLeft(index, clientWidth, scrollWidth) {
  const page = clientWidth - 1;
  const target = index * page;
  if (typeof scrollWidth === "number") {
    // The browser will not scroll past the end, so asking for more is asking
    // for a position that never happens and reads back as the wrong page.
    const maxScroll = scrollWidth - clientWidth;
    return Math.min(target, Math.max(0, maxScroll));
  }
  return target;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { railPages, railPage, railScrollLeft };
}
if (typeof window !== "undefined") {
  window.ITMoviesRail = { railPages, railPage, railScrollLeft };
}
