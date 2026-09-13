/**
 * Two drawings for the explainer.
 *
 * Inline SVG for the reason the wordmark gives: they inherit `currentColor` so
 * they follow the theme without a second asset, and they cost no request. That
 * last part is not a micro-optimisation here — `docs/SCREENS.md` asks for help
 * that "works without signal", and the service worker precaches the shell but
 * deliberately caches nothing at runtime (ADR-005). A drawing that arrives over
 * the network is a drawing that is missing on the first tee.
 *
 * Both are `aria-hidden`: everything they show is said in the prose beside them,
 * and a screen reader announcing "three circles" adds nothing.
 */

/** Three holes, linked — the loop, which is the whole competition. */
export function LoopDiagram() {
  return (
    <svg className="diagram" viewBox="0 0 120 40" fill="none" aria-hidden="true">
      <line x1="20" y1="20" x2="60" y2="20" stroke="currentColor" strokeWidth="2" />
      <line x1="60" y1="20" x2="100" y2="20" stroke="currentColor" strokeWidth="2" />
      {[20, 60, 100].map((x) => (
        <circle key={x} cx={x} cy="20" r="9" stroke="currentColor" strokeWidth="2" />
      ))}
      <text x="20" y="24.5" textAnchor="middle" fontSize="10" fill="currentColor">
        1
      </text>
      <text x="60" y="24.5" textAnchor="middle" fontSize="10" fill="currentColor">
        2
      </text>
      <text x="100" y="24.5" textAnchor="middle" fontSize="10" fill="currentColor">
        3
      </text>
    </svg>
  );
}

/**
 * The group, drawn as the wordmark is.
 *
 * The mark has always been a ball whose dimples read as three, and that has
 * never been said to anyone. Here is the one screen where saying it is the
 * point, so the drawing is deliberately the same shape.
 */
export function GroupDiagram() {
  return (
    <svg className="diagram" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="8.4" r="1.8" fill="currentColor" />
      <circle cx="8.9" cy="13.8" r="1.8" fill="currentColor" />
      <circle cx="15.1" cy="13.8" r="1.8" fill="currentColor" />
    </svg>
  );
}
