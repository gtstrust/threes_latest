/**
 * Add holes to a course that doesn't have enough of them yet.
 *
 * A loop is three holes (ADR-004), so a course with fewer than that can't have
 * a round drawn against it. This is the only frontend surface for
 * `PUT /courses/{id}/holes` — it existed on the backend already, but nothing
 * called it for a course picked from the dropdown rather than created fresh.
 */

import { useState } from 'react';

import { ErrorNote } from '../../components/ui';
import { useUpsertHoles } from '../../lib/queries';
import type { UUID } from '../../lib/types';

const MAX_HOLES = 18;

export function CourseHolesEditor({
  courseId,
  currentCount,
}: {
  courseId: UUID;
  currentCount: number;
}) {
  const upsertHoles = useUpsertHoles(courseId);
  const [addCount, setAddCount] = useState(Math.min(3, MAX_HOLES - currentCount));

  const remaining = MAX_HOLES - currentCount;
  if (remaining <= 0) return null;

  function handleAdd() {
    // Additive, matched on hole number — this only ever appends past whatever
    // is already there, so an existing hole's par is never touched.
    const holes = Array.from({ length: addCount }, (_, index) => ({
      hole_number: currentCount + index + 1,
    }));
    upsertHoles.mutate(holes, {
      onSuccess: () => setAddCount(Math.min(3, MAX_HOLES - (currentCount + holes.length))),
    });
  }

  return (
    <>
      <p className="muted small">
        {currentCount} hole{currentCount === 1 ? '' : 's'} entered
        {currentCount < 3 && ' — a loop needs at least 3 before a round can be drawn'}.
      </p>
      <label htmlFor={`add-holes-${courseId}`}>Add holes</label>
      <input
        id={`add-holes-${courseId}`}
        type="number"
        inputMode="numeric"
        min={1}
        max={remaining}
        value={addCount}
        onChange={(event) => setAddCount(Number(event.target.value))}
      />
      <button type="button" onClick={handleAdd} disabled={upsertHoles.isPending || addCount < 1}>
        {upsertHoles.isPending ? 'Adding…' : `Add ${addCount} hole${addCount === 1 ? '' : 's'}`}
      </button>
      <ErrorNote error={upsertHoles.error} />
    </>
  );
}
