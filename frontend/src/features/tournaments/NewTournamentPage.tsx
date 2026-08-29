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

import { Card, ErrorNote, Page } from '../../components/ui';
import { useCoursePicker } from '../courses/CoursePicker';
import { useCreateTournament } from '../../lib/queries';

export function NewTournamentPage() {
  const navigate = useNavigate();
  const picker = useCoursePicker();
  const createTournament = useCreateTournament();

  const [name, setName] = useState('');
  // Empty means no cap, which is the default and the common case.
  const [cap, setCap] = useState('');
  const [failed, setFailed] = useState<unknown>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFailed(null);
    try {
      const chosen = await picker.resolveCourseId();
      const tournament = await createTournament.mutateAsync({
        name,
        ...(chosen ? { course_id: chosen } : {}),
        ...(cap ? { max_players: Number(cap) } : {}),
      });
      void navigate(`/t/${tournament.id}`);
    } catch (error) {
      // Without this the rejection escapes the form entirely: the tournament is
      // not created and nothing on screen says why.
      setFailed(error);
    }
  }

  const busy = picker.busy || createTournament.isPending;

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

          {picker.element}

          <label htmlFor="cap">Maximum players (optional)</label>
          <input
            id="cap"
            type="number"
            inputMode="numeric"
            min={2}
            value={cap}
            onChange={(event) => setCap(event.target.value)}
            placeholder="No limit"
          />
          <p className="muted small">
            Stops the field growing past what you booked. Only applies to players joining themselves
            — you can always add someone yourself.
          </p>

          <button type="submit" disabled={busy || !name || picker.blocked}>
            {busy ? 'Creating…' : 'Create tournament'}
          </button>
        </form>
        <ErrorNote error={failed ?? picker.error ?? createTournament.error} />
      </Card>
    </Page>
  );
}
