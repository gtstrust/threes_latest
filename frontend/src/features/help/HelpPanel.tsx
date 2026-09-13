/**
 * The help a screen carries about itself.
 *
 * A `<details>` rather than a button with a panel, for the same reason the
 * appearance radios and the sign-in inputs are plain HTML controls: open and
 * close, the keyboard, and the screen-reader announcement all come for free and
 * all work the first time. There is no state to get wrong.
 *
 * **It opens in place and never navigates.** The screen this matters most on is
 * score entry, where the person reading it is standing on a green with a
 * half-entered card and one hand free. Sending them to a different route to find
 * out what "closest to the pin" means would lose the card and the thread at once,
 * which is why the panel answers here and only *offers* the walkthrough.
 *
 * It sits under the page title rather than inside it: a disclosure that pushes
 * content down is honest about what it is doing, where a floating panel on a
 * phone covers the thing being asked about.
 */

import { Link } from 'react-router-dom';

import { TOPICS } from './content';

export function HelpPanel({ topic }: { topic: string }) {
  const help = TOPICS[topic];
  // An unknown key renders nothing rather than throwing. A missing help panel is
  // a screen that is no worse than it was yesterday; a crash is a white screen on
  // a tee. `content.test.ts` is what actually keeps the keys honest.
  if (!help) return null;

  return (
    <details className="help">
      <summary>
        <span aria-hidden="true" className="help-mark">
          ?
        </span>
        {help.title}
      </summary>
      <div className="help-body">
        {help.body.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
        <Link to={`/how-it-works?step=${help.step}`}>How Threes works</Link>
      </div>
    </details>
  );
}
