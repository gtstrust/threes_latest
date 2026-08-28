/**
 * Picking or creating a course — shared by the new-tournament and new-fun-round
 * screens, which both need exactly this and nothing more.
 *
 * Exposed as a hook rather than a component so the parent keeps ownership of its
 * own submit: `resolveCourseId()` creates or tops up the course and returns its
 * id, or returns the chosen existing id, or `''` for "decide later". The course
 * id travels with the upsert call, so a freshly created course is targeted
 * correctly within the same submit.
 *
 * It also reports `holeNumbers` — which holes the chosen course will have once
 * this submit lands — because the caller may need to offer a loop from them, and
 * only this hook knows whether the course exists yet.
 */

import { useState, type ReactNode } from 'react';

import { Loading } from '../../components/ui';
import { useCourse, useCourses, useCreateCourse, useUpsertHoles } from '../../lib/queries';
import { useSession } from '../auth/session-context';

/** A 3-hole loop is the format, so anything playable is a multiple of three. */
const DEFAULT_HOLES = 18;

/** Scoring needs holes, and a loop is three of them. Below this, nothing can be drawn. */
const HOLES_PER_LOOP = 3;

export type CoursePicker = {
  element: ReactNode;
  /** Resolve to a course id, creating or topping up the course first. `''` = decide later. */
  resolveCourseId: () => Promise<string>;
  /** The hole numbers the chosen course will have, for building a loop from. */
  holeNumbers: number[];
  /** True while the choice can't be acted on — a course with no holes nobody can add. */
  blocked: boolean;
  busy: boolean;
  error: unknown;
};

const upTo = (count: number) => Array.from({ length: count }, (_, index) => index + 1);

export function useCoursePicker({ defaultHoles = DEFAULT_HOLES } = {}): CoursePicker {
  const { player } = useSession();
  const courses = useCourses();
  const createCourse = useCreateCourse();
  const upsertHoles = useUpsertHoles();

  const [courseId, setCourseId] = useState('');
  const [newCourseName, setNewCourseName] = useState('');
  const [holeCount, setHoleCount] = useState(defaultHoles);

  const makingCourse = courseId === 'new';
  const chosen = courses.data?.find((course) => course.id === courseId);
  // Only fetched for an existing course, and only its hole numbers are used.
  const detail = useCourse(chosen ? courseId : null);

  // A course with too few holes can't be played. Whoever created it can fix that
  // here — courses are shared reference data, so nobody else may (the API would
  // answer 403), and offering the control to them would be a lie.
  const needsHoles = Boolean(chosen) && (chosen?.hole_count ?? 0) < HOLES_PER_LOOP;
  const canAddHoles = needsHoles && chosen?.created_by === player?.id;
  const blocked = needsHoles && !canAddHoles;

  const holeNumbers = makingCourse
    ? upTo(holeCount)
    : canAddHoles
      ? upTo(holeCount)
      : (detail.data?.holes.map((hole) => hole.hole_number) ?? []);

  async function resolveCourseId(): Promise<string> {
    // The endpoint takes the whole set of holes being played, not a delta, and
    // adds rather than replaces — so sending 1..n is safe on a course that
    // already has some.
    const holes = upTo(holeCount).map((hole_number) => ({ hole_number }));

    if (makingCourse) {
      const course = await createCourse.mutateAsync({ name: newCourseName });
      await upsertHoles.mutateAsync({ courseId: course.id, holes });
      return course.id;
    }

    if (canAddHoles) await upsertHoles.mutateAsync({ courseId, holes });
    return courseId;
  }

  const holesField = (
    <>
      <label htmlFor="holes">Holes on the course</label>
      <input
        id="holes"
        type="number"
        inputMode="numeric"
        min={HOLES_PER_LOOP}
        max={18}
        value={holeCount}
        onChange={(event) => setHoleCount(Number(event.target.value))}
      />
      <p className="muted small">
        Only the holes being played need to exist. Par is optional — scoring never uses it.
      </p>
    </>
  );

  const element = (
    <>
      <label htmlFor="course">Course</label>
      {courses.isPending ? (
        <Loading what="Loading courses" />
      ) : (
        <select id="course" value={courseId} onChange={(event) => setCourseId(event.target.value)}>
          <option value="">Decide later</option>
          {courses.data?.map((course) => (
            <option key={course.id} value={course.id}>
              {/* The count is on the label because it decides whether the course
                  can be played at all, and finding that out at the tee is the
                  failure this is here to prevent. */}
              {course.name} — {course.hole_count || 'no'} holes
            </option>
          ))}
          <option value="new">Add a new course…</option>
        </select>
      )}

      {makingCourse && (
        <>
          <label htmlFor="course-name">New course name</label>
          {/* Names are unique ignoring case — two organisers at the same club
              point at one record rather than each making their own. */}
          <input
            id="course-name"
            required
            value={newCourseName}
            onChange={(event) => setNewCourseName(event.target.value)}
            placeholder="Royal Melbourne"
          />
          {holesField}
        </>
      )}

      {canAddHoles && (
        <>
          <p className="muted small">
            {chosen?.name} has no holes entered yet, so there&rsquo;s nothing to play. Add them now
            — you created it, so you can.
          </p>
          {holesField}
        </>
      )}

      {blocked && (
        <p className="muted small">
          {chosen?.name} has no holes entered, and only whoever created it can add them. Pick
          another course, or add a new one.
        </p>
      )}
    </>
  );

  return {
    element,
    resolveCourseId,
    holeNumbers,
    blocked,
    busy: createCourse.isPending || upsertHoles.isPending,
    error: createCourse.error ?? upsertHoles.error,
  };
}
