/**
 * The organiser's event settings: everything about the day that isn't the field
 * or the draw.
 *
 * The date is the reason this screen exists. `scheduled_at` has been on the
 * model since M2 and settable through the API, but nothing in the app ever set
 * it — and the day-before reminder sweep only looks at events that have one. An
 * event created here without a date is an event whose players are never told.
 */

import { useState, type FormEvent } from 'react';

import { Card, ErrorNote, Loading, Page } from '../../components/ui';
import { useCourse, useCourses, useTournament, useUpdateTournament } from '../../lib/queries';
import { useSession } from '../auth/session-context';
import type { UUID } from '../../lib/types';
import { toInstant, toLocalInput } from './when';

export function TournamentSettingsPage({ tournamentId }: { tournamentId: UUID }) {
  const tournament = useTournament(tournamentId);
  const courses = useCourses();
  const { player } = useSession();

  if (tournament.isPending) return <Loading what="Loading the event" />;
  if (tournament.error || !tournament.data)
    return (
      <Page title="Event settings" back={{ to: `/t/${tournamentId}`, label: 'Tournament' }}>
        <ErrorNote error={tournament.error} />
      </Page>
    );

  if (tournament.data.organiser_id !== player?.id)
    return (
      <Page title="Event settings" back={{ to: `/t/${tournamentId}`, label: 'Tournament' }}>
        <Card>
          <h2>Not yours to change</h2>
          <p className="muted">Only the organiser can edit this event.</p>
        </Card>
      </Page>
    );

  return (
    <Page title="Event settings" back={{ to: `/t/${tournamentId}`, label: 'Tournament' }}>
      <SettingsForm
        tournamentId={tournamentId}
        name={tournament.data.name}
        courseId={tournament.data.course_id}
        scheduledAt={tournament.data.scheduled_at}
        maxPlayers={tournament.data.max_players}
        courses={courses.data ?? []}
      />
    </Page>
  );
}

function SettingsForm({
  tournamentId,
  name: initialName,
  courseId: initialCourse,
  scheduledAt,
  maxPlayers,
  courses,
}: {
  tournamentId: UUID;
  name: string;
  courseId: UUID | null;
  scheduledAt: string | null;
  maxPlayers: number | null;
  courses: { id: UUID; name: string; hole_count: number }[];
}) {
  const update = useUpdateTournament(tournamentId);

  const [name, setName] = useState(initialName);
  const [courseId, setCourseId] = useState(initialCourse ?? '');
  const [when, setWhen] = useState(toLocalInput(scheduledAt));
  const [cap, setCap] = useState(maxPlayers === null ? '' : String(maxPlayers));

  const course = useCourse(courseId || null);
  const holes = course.data?.holes.length ?? 0;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    update.mutate({
      name,
      // Explicit nulls, not omissions: the API leaves an omitted field alone, so
      // clearing a date or a cap is only expressible this way.
      course_id: courseId || null,
      scheduled_at: toInstant(when),
      max_players: cap === '' ? null : Number(cap),
    });
  }

  return (
    <Card>
      <form onSubmit={onSubmit}>
        <label htmlFor="name">Event name</label>
        <input id="name" required value={name} onChange={(e) => setName(e.target.value)} />

        <label htmlFor="course">Course</label>
        <select id="course" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
          <option value="">Decide later</option>
          {courses.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name} — {option.hole_count || 'no'} holes
            </option>
          ))}
        </select>
        {courseId && holes > 0 && holes < 3 && (
          <p className="muted small">
            This course has {holes} hole{holes === 1 ? '' : 's'} entered. A loop needs three.
          </p>
        )}

        <label htmlFor="when">Date and tee time</label>
        <input
          id="when"
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
        />
        <p className="muted small">
          Players are emailed a reminder the day before. Without a date, no reminder goes out.
        </p>

        <label htmlFor="cap">Maximum players</label>
        <input
          id="cap"
          type="number"
          inputMode="numeric"
          min={2}
          value={cap}
          onChange={(e) => setCap(e.target.value)}
          placeholder="No limit"
        />
        <p className="muted small">
          Only players joining themselves are stopped — you can always add someone yourself.
        </p>

        <button type="submit" disabled={update.isPending || !name}>
          {update.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </form>
      {update.isSuccess && !update.isPending && <p className="muted small">Saved.</p>}
      <ErrorNote error={update.error} />
    </Card>
  );
}
