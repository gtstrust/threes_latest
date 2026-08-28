/**
 * Picking or creating a course — shared by the new-tournament and new-fun-round
 * screens, which both need exactly this and nothing more.
 *
 * Exposed as a hook rather than a component so the parent keeps ownership of its
 * own submit: `resolveCourseId()` creates the course (if the picker is on "new")
 * and returns its id, or returns the chosen existing id, or `''` for "decide
 * later". The course id travels with the upsert call, so a freshly created course
 * is targeted correctly within the same submit.
 */

import { useState, type ReactNode } from 'react';

import { Loading } from '../../components/ui';
import { useCourses, useCreateCourse, useUpsertHoles } from '../../lib/queries';

/** A 3-hole loop is the format, so anything playable is a multiple of three. */
const DEFAULT_HOLES = 18;

export type CoursePicker = {
  element: ReactNode;
  /** Resolve to a course id, creating the course if the picker is on "new". `''` = decide later. */
  resolveCourseId: () => Promise<string>;
  busy: boolean;
  error: unknown;
};

export function useCoursePicker({ defaultHoles = DEFAULT_HOLES } = {}): CoursePicker {
  const courses = useCourses();
  const createCourse = useCreateCourse();
  const upsertHoles = useUpsertHoles();

  const [courseId, setCourseId] = useState('');
  const [newCourseName, setNewCourseName] = useState('');
  const [holeCount, setHoleCount] = useState(defaultHoles);

  const makingCourse = courseId === 'new';

  async function resolveCourseId(): Promise<string> {
    if (!makingCourse) return courseId;
    const course = await createCourse.mutateAsync({ name: newCourseName });
    // The endpoint takes the whole set of holes, not a delta — a course only
    // needs the holes actually being played, so three is a valid course.
    await upsertHoles.mutateAsync({
      courseId: course.id,
      holes: Array.from({ length: holeCount }, (_, index) => ({ hole_number: index + 1 })),
    });
    return course.id;
  }

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
              {course.name}
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
          <label htmlFor="holes">Holes on the course</label>
          <input
            id="holes"
            type="number"
            inputMode="numeric"
            min={3}
            max={18}
            value={holeCount}
            onChange={(event) => setHoleCount(Number(event.target.value))}
          />
          <p className="muted small">
            Only the holes being played need to exist. Par is optional — scoring never uses it.
          </p>
        </>
      )}
    </>
  );

  return {
    element,
    resolveCourseId,
    busy: createCourse.isPending || upsertHoles.isPending,
    error: createCourse.error ?? upsertHoles.error,
  };
}
