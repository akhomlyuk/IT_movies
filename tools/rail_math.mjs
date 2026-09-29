// Exercises the real rail math that js/film.js runs in the browser --
// js/rail_math.js is loaded as a plain <script> there, and required here, so a
// change to the formula cannot pass this test while the page keeps the old one.
//
// Run: node tools/rail_math.mjs

import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { railPages, railPage, railScrollLeft } = require("../js/rail_math.js");

const cases = [
  // [clientWidth, scrollWidth, expected, why]
  [849, 1080, 2, "231px of hidden strip is a second page, not zero"],
  [322, 1080, 4, "375px viewport: four pages of scrolling"],
  [617, 1080, 2, "768px viewport: two pages"],
  [226, 1080, 5, "one card per page at xs, six cards"],
  [1040, 1040, 1, "nothing to scroll"],
  [1040, 1041, 1, "1px of slack is not a page"],
  [1040, 1042, 2, "2px past the edge is a second page"],
];

let failed = 0;
for (const [cw, sw, want, why] of cases) {
  const got = railPages(cw, sw);
  if (got !== want) {
    failed++;
    console.error(`FAIL railPages(${cw}, ${sw}) = ${got}, want ${want} (${why})`);
  } else {
    console.log(`ok   railPages(${cw}, ${sw}) = ${got} — ${why}`);
  }
}

// The last page must actually reach the end, and the index must stay in range
// for every scroll position the strip can take.
const geometry = [
  [849, 1080],
  [322, 1080],
  [226, 1080],
  [1040, 1080],
];
for (const [cw, sw] of geometry) {
  const pages = railPages(cw, sw);
  const maxScroll = sw - cw;
  for (let left = 0; left <= maxScroll; left += 7) {
    const idx = railPage(left, cw, sw, pages);
    if (idx < 0 || idx >= pages) {
      failed++;
      console.error(`FAIL railPage(${left}, ${cw}, ${sw}, ${pages}) = ${idx}, out of range`);
      break;
    }
  }
  // Sitting at the very end must read as the last page. The browser clamps
  // scrollLeft to maxScroll, which on a short last page is nowhere near
  // (pages - 1) * pageWidth, so a pure round(scrollLeft / page) lands on page 0
  // and leaves "previous" disabled at the end of the strip.
  const atEnd = railPage(maxScroll, cw, sw, pages);
  if (atEnd !== pages - 1) {
    failed++;
    console.error(
      `FAIL railPage at the end of ${cw}/${sw} = ${atEnd}, want ${pages - 1}`
    );
  } else {
    console.log(`ok   railPage at the end of ${cw}/${sw} = ${atEnd} (last of ${pages})`);
  }
  // A click on "next" must be able to land on the last page: the target offset
  // has to be clamped to what the browser will actually allow.
  const target = railScrollLeft(pages - 1, cw, sw);
  if (target < maxScroll) {
    failed++;
    console.error(
      `FAIL next on the last page of ${cw}/${sw} targets ${target}, short of ${maxScroll}`
    );
  } else {
    console.log(`ok   next on the last page of ${cw}/${sw} targets ${target} (end ${maxScroll})`);
  }
}

console.log(failed ? `${failed} failed` : "rail math: all cases pass");
process.exit(failed ? 1 : 0);
