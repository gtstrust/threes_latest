/**
 * A join link as a QR, drawn as inline SVG.
 *
 * SVG rather than canvas because this gets shown from a phone held up at
 * registration, screenshotted into an email, and occasionally printed — all of
 * which want something that scales. It also means no ref, no effect, and nothing
 * to clean up: the whole component is a function of its text.
 *
 * Error correction level M, the usual default: enough redundancy to survive a
 * fingerprint on the screen without inflating the module count.
 */

import { useMemo } from 'react';
import qrcode from 'qrcode-generator';

/** A quiet zone is part of the spec — without it scanners hunt for the edges. */
const QUIET_ZONE = 4;

export function QrCode({ text, label }: { text: string; label: string }) {
  const { count, path } = useMemo(() => {
    const code = qrcode(0, 'M');
    code.addData(text);
    code.make();

    const modules = code.getModuleCount();
    // One path of many little squares beats one <rect> per module: a 29×29 code
    // is 841 potential nodes, and the browser lays out every one of them.
    const parts: string[] = [];
    for (let row = 0; row < modules; row += 1) {
      for (let column = 0; column < modules; column += 1) {
        if (code.isDark(row, column)) {
          parts.push(`M${column + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`);
        }
      }
    }
    return { count: modules + QUIET_ZONE * 2, path: parts.join('') };
  }, [text]);

  return (
    <svg
      className="qr"
      viewBox={`0 0 ${count} ${count}`}
      role="img"
      aria-label={label}
      shapeRendering="crispEdges"
    >
      {/* The light modules have to be painted, not left transparent: a dark page
          behind a transparent QR inverts it, and an inverted code won't scan. */}
      <rect width={count} height={count} fill="#ffffff" />
      <path d={path} fill="#000000" />
    </svg>
  );
}
