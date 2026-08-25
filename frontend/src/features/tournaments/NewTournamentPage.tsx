/**
 * Setting up an event: pick or create a course, then create the tournament.
 *
 * Both in one screen because they are one job. A tournament can exist without a
 * course — `course_id` is nullable so an event can be set up before the venue is
 * booked — but it cannot start play without one, so making the organiser visit
 * two screens would only defer the same work.
 */

import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { Card, ErrorNote, Loading, Page } from '../../components/ui';
import { useCourses, useCreateCourse, useCreateTournament, useUpsertHoles } from '../../lib/queries';

/** A 3-hole loop is the format, so anything playable is a multiple of three. */
const DEFAULT_HOLES = 18;

export function NewTournamentPage() {
  const navigate = useNavigate();
  const courses = useCourses();
  const createCourse = useCreateCourse();
  const upsertHoles = useUpsertHoles(createCourse.data?.id ?? '');
  const createTournament = useCreateTournament();

  const [name, setName] = useState('');
  const [courseId, setCourseId] = useState('');
  const [newCourseName, setNewCourseName] = useState('');
  const [holeCount, setHoleCount] = useState(DEFAULT_HOLES);

  const makingCourse = courseId === 'new';

  async function onSubmit(event: FormEvent) {
    event.preventDefault();

    let chosen = courseId;
    if (makingCourse) {
      const course = await createCourse.mutateAsync({ name: newCourseName });
      // The endpoint takes the whole set of holes, not a delta — so send them
      // all. A course only needs the holes actually being played: three is a
      // valid course if that is the loop.
      await upsertHoles.mutateAsync(
        Array.from({ length: holeCount }, (_, index) => ({ hole_number: index + 1 })),
      );
      chosen = course.id;
    }

    const tournament = await createTournament.mutateAsync({
      name,
      ...(chosen ? { course_id: chosen } : {}),
    });
    void navigate(`/t/${tournament.id}`);
  }

  const busy = createCourse.isPending || upsertHoles.isPending || createTournament.isPending;

  return (
    <Page title="New tournament" back={{ to: '/', label: 'Tournaments' }}>
      <Card>
        <form onSubmit={onSubmit}>
          <label htmlFor="name">Tournament name</label>
          <input
            id="name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Acme Corporate Day"
          />

          <label htmlFor="course">Course</label>
          {courses.isPending ? (
            <Loading what="Loading courses" />
          ) : (
            <select
              id="course"
              value={courseId}
              onChange={(event) => setCourseId(event.target.value)}
            >
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

          <button type="submit" disabled={busy || !name}>
            {busy ? 'Creating…' : 'Create tournament'}
          </button>
        </form>
        <ErrorNote error={createCourse.error ?? upsertHoles.error ?? createTournament.error} />
      </Card>
    </Page>
  );
}
