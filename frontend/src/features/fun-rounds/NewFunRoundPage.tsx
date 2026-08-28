/**
 * Starting a fun round: name it, pick or create a course, choose the three holes,
 * and you're the host in a lobby your mates can join by link.
 *
 * The loop is chosen here rather than at the tee. Which three holes you're playing
 * is part of deciding where you're playing, and leaving it until start means the
 * host discovers a course has no usable holes with everyone already standing on
 * it — which is exactly what happened before.
 */

import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { Card, ErrorNote, Page } from '../../components/ui';
import { useCoursePicker } from '../courses/CoursePicker';
import { useCreateFunRound } from '../../lib/queries';

const HOLES_PER_LOOP = 3;

/** The loops a course offers: consecutive triples, whatever's left over unused. */
function loopsFrom(holeNumbers: number[]): number[][] {
  const loops: number[][] = [];
  for (let index = 0; index + HOLES_PER_LOOP <= holeNumbers.length; index += HOLES_PER_LOOP) {
    loops.push(holeNumbers.slice(index, index + HOLES_PER_LOOP));
  }
  return loops;
}

export function NewFunRoundPage() {
  const navigate = useNavigate();
  const picker = useCoursePicker({ defaultHoles: 3 });
  const createFunRound = useCreateFunRound();

  const [name, setName] = useState('');
  const [loopIndex, setLoopIndex] = useState(0);
  const [failed, setFailed] = useState<unknown>(null);

  const loops = loopsFrom(picker.holeNumbers);
  // One loop is no choice at all — a 3-hole course plays its only three.
  const chooseable = loops.length > 1;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFailed(null);
    try {
      const chosen = await picker.resolveCourseId();
      const holes = loops[loopIndex];
      const funRound = await createFunRound.mutateAsync({
        name,
        ...(chosen ? { course_id: chosen } : {}),
        ...(chosen && holes ? { hole_numbers: holes } : {}),
      });
      void navigate(`/r/${funRound.id}`);
    } catch (error) {
      // Without this the rejection escapes the form entirely: the round is not
      // created and nothing on screen says why.
      setFailed(error);
    }
  }

  const busy = picker.busy || createFunRound.isPending;

  return (
    <Page title="New fun round" back={{ to: '/', label: 'Home' }}>
      <Card>
        <form onSubmit={onSubmit}>
          <label htmlFor="name">What are you playing?</label>
          <input
            id="name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Saturday nine"
          />

          {picker.element}

          {chooseable && (
            <>
              <label htmlFor="loop">Which three holes?</label>
              <select
                id="loop"
                value={loopIndex}
                onChange={(event) => setLoopIndex(Number(event.target.value))}
              >
                {loops.map((loop, index) => (
                  <option key={loop.join('-')} value={index}>
                    Holes {loop.join(', ')}
                  </option>
                ))}
              </select>
            </>
          )}

          <button type="submit" disabled={busy || !name || picker.blocked}>
            {busy ? 'Starting…' : 'Start a fun round'}
          </button>
        </form>
        <ErrorNote error={failed ?? picker.error ?? createFunRound.error} />
      </Card>
    </Page>
  );
}
