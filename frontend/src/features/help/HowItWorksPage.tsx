/**
 * The explainer, stepped.
 *
 * The screen this app most needed and did not have. `docs/SCREENS.md` ranks it
 * first of every gap for a reason worth restating: a corporate guest scans a QR
 * on the first tee, signs in, taps "I'm in", and the next thing they meet asks
 * how many strokes they took — with nothing anywhere having explained the
 * three-hole format, that only one of them can win a hole, or why it suddenly
 * wants to know who was closest to the pin.
 *
 * **Public, and that is the point.** This is the only route outside `RequireAuth`
 * (see `App.tsx`). The moment somebody most wants to know what Threes is comes
 * when they are handed an invitation, and that is before they have an account —
 * so making them sign in to find out would put the answer on the wrong side of
 * the question. It carries no player, event or score data, so there is nothing
 * here to protect.
 *
 * Stepped rather than one long page because the format is unfamiliar: one idea
 * at a time, with somewhere to stop. The step lives in the URL so a help panel
 * can open the explainer at the part that answers it, and so Back walks the
 * steps rather than leaving the screen.
 */

import type { ReactElement } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { Card, Page } from '../../components/ui';
import { useSession } from '../auth/session-context';
import { findStep, stepsFor } from './content';
import { GroupDiagram, LoopDiagram } from './diagrams';

/** The drawing that belongs with a step, where one does. Most have none. */
const DIAGRAMS: Record<string, () => ReactElement> = {
  format: LoopDiagram,
  group: GroupDiagram,
};

export function HowItWorksPage() {
  const [params, setParams] = useSearchParams();
  // Signed in or not — this route is outside the auth guard, so both are normal.
  // `player` is the stricter test of the two: a verified token does not imply a
  // profile row, and "Your golf" would 404 for somebody mid-provisioning.
  const { player } = useSession();

  const { step, index, of } = findStep(params.get('step'));
  const previous = of[index - 1];
  const next = of[index + 1];
  const Diagram = DIAGRAMS[step.id];

  // `replace` so the whole walkthrough is one history entry from the caller's
  // point of view: somebody who reads six steps and presses the system back
  // button wants the screen they came from, not step five.
  const goTo = (id: string) => setParams({ step: id }, { replace: true });

  const organiser = stepsFor('organiser');
  const lastPlayerStep = !next && step.track === 'player';

  return (
    <Page
      title="How Threes works"
      back={player ? { to: '/', label: 'Your golf' } : undefined}
      actions={
        next ? (
          // A way out that is not the last step. Somebody who already knows the
          // format should not have to tap Next six times to leave.
          <Link to="/" className="muted small">
            Skip
          </Link>
        ) : undefined
      }
    >
      <p className="muted small">
        {step.track === 'organiser' ? 'Running an event' : 'Playing'} · step {index + 1} of{' '}
        {of.length}
      </p>

      <ol className="walk-dots" aria-hidden="true">
        {of.map((each, position) => (
          <li key={each.id} className={position <= index ? 'done' : undefined} />
        ))}
      </ol>

      <Card>
        <h2>{step.title}</h2>
        {Diagram && <Diagram />}
        {step.body.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </Card>

      <nav className="walk-nav" aria-label="Through the explainer">
        {previous ? (
          <button type="button" className="ghost" onClick={() => goTo(previous.id)}>
            Back
          </button>
        ) : (
          // Holds the column so "Next" does not slide left on the first step.
          <span />
        )}
        {next ? (
          <button type="button" onClick={() => goTo(next.id)}>
            Next
          </button>
        ) : (
          <Link to="/" className="button-link">
            Done
          </Link>
        )}
      </nav>

      {lastPlayerStep && organiser.length > 0 && (
        <p className="muted small">
          Running an event yourself?{' '}
          <button type="button" className="link" onClick={() => goTo(organiser[0].id)}>
            How to run one
          </button>
        </p>
      )}
    </Page>
  );
}
