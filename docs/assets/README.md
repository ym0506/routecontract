# README visual assets

`routecontract-banner.png` is original editorial artwork produced with the built-in image generation tool. It is a brand illustration, not a product screenshot, route plan, execution trace or performance result. Its wordmark and tagline are also available in the README image alternative text.

`execution-comparison.svg` is an editable illustration authored in SVG. Counts and codes come from the checked-in [MySQL manifests](../../examples/manifests/README.md) and [CI report](../evidence/ci-review-report-example.md): one unchanged business row, observed physical JDBC attempts 1 → 2, observed data-source aliases 1 → 2, RCM201 / RCM202. The illustration does not constitute an additional experiment. Existing `submission/assets` evidence artwork is unchanged.

## Banner generation prompt

```text
Use case: ads-marketing.
Asset type: a polished wide GitHub README header banner for the open-source Java testing library RouteContract.
Primary request: create a restrained, distinctive developer-tool identity around observing changes in database execution. This is an editorial brand illustration, not a screenshot, benchmark, actual execution trace, or proof of a route plan.
Composition: very wide landscape approximately 3:1 (1800 by 600 or equivalent). Warm near-white canvas with generous clean margins; crisp dark ink typography on the left, and a refined small abstract circuit illustration on the right. Left two-thirds contains the wordmark and tagline with generous whitespace. Right third depicts a single thin ink path splitting gently toward a few small rounded geometric endpoints, one quiet blue accent and one muted amber accent, subtly suggesting a changed execution path under inspection. Flat editorial vector-like illustration, elegant precise geometry, no 3D gloss, no neon glow, no dark futuristic background.
Text exactly: "RouteContract" as the large primary wordmark in a tasteful modern sans serif, and below it "Test the execution behind the result." as one smaller line. No other words or numbers.
Palette: warm ivory #FAF9F6, deep ink #182C38, restrained blue #277DA1 and amber #D99B32.
Constraints: beautiful and readable when scaled to an 850px-wide GitHub README. Text and illustration visually balanced. No badges, charts, performance numbers, test status, customer logos, Apache logo, mascot, watermark, extra copy, or fabricated product interface. Avoid generic AI network meshes and excessive decorative elements. Deliver a single finished banner image.
```

## Final framing edit prompt

```text
Edit this exact RouteContract banner for a compact GitHub README header. Preserve the exact existing wordmark, tagline, palette and abstract branch illustration. Change only the canvas framing: trim excess empty space above and below so the final image is a very wide approximately 3:1 aspect ratio, roughly 1800x600. Keep all existing text and the full visible branch illustration intact with comfortable 48px margins. Do not add or change any text, objects, colors, styling or branding. The desired effect is the same banner with less empty vertical padding and a shorter height on a README.
```

The final banner is 2172 × 724 pixels. Its fixed ivory canvas keeps the wordmark readable in either GitHub theme. The comparison diagram has descriptive title/description elements; each README also supplies its complete comparison as alternative text and explains the scope in prose.
