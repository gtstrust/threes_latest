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
import { HelpPanel } from '../help/HelpPanel';
import { useCoursePicker } from '../courses/CoursePicker';
import { useCreateTournament } from '../../lib/queries';
import type { TournamentFormat } from '../../lib/types';
import { describeBracket } from './knockout';

export function NewTournamentPage() {
  const navigate = useNavigate();
  const picker = useCoursePicker();
  const createTournament = useCreateTournament();

  const [name, setName] = useState('');
  // Empty means no cap, which is the default and the common case.
  const [cap, setCap] = useState('');
  // Create-only: after round one a knockout has stored verdicts and a round
  // robin has none, so there is no coherent way to switch later (ADR-012).
  const [format, setFormat] = useState<TournamentFormat>('ROUND_ROBIN');
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
        // Sent only when it is not the default, so a round robin's request body
        // is exactly what it always was.
        ...(format === 'KNOCKOUT' ? { format } : {}),
      });
      void navigate(`/t/${tournament.id}`);
    } catch (error) {
      // Without this the rejection escapes the form entirely: the tournament is
      // not created and nothing on screen says why.
      setFailed(error);
    }
  }

  const busy = picker.busy || createTournament.isPending;
  // The cap is the only field size known before anyone joins, so it is what
  // the bracket preview has to work from. Fourballs: the group size is set on
  // the settings screen after creation, and threes is still the default there.
  const bracket = cap ? describeBracket(Number(cap), 4) : null;

  return (
    <Page title="New tournament" back={{ to: '/', label: 'Tournaments' }}>
      <HelpPanel topic="formats" />

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

          <fieldset>
            <legend>Format</legend>
            <label htmlFor="round-robin">
              <input
                id="round-robin"
                type="radio"
                name="format"
                value="ROUND_ROBIN"
                checked={format === 'ROUND_ROBIN'}
                onChange={() => setFormat('ROUND_ROBIN')}
              />{' '}
              Round robin — everyone plays every round, and the leaderboard adds up.
            </label>
            <label htmlFor="knockout">
              <input
                id="knockout"
                type="radio"
                name="format"
                value="KNOCKOUT"
                checked={format === 'KNOCKOUT'}
                onChange={() => setFormat('KNOCKOUT')}
              />{' '}
              Knockout — each group's winner goes through. Everyone else is done.
            </label>
          </fieldset>
          {format === 'KNOCKOUT' && bracket && <p className="muted small">{bracket}</p>}
          {format === 'KNOCKOUT' && !bracket && (
            <p className="muted small">
              Set a maximum to see how the bracket falls out. Most players are knocked out in
              the first round, so it is worth knowing the shape before you invite anyone.
            </p>
          )}

          <button type="submit" disabled={busy || !name || picker.blocked}>
            {busy ? 'Creating…' : 'Create tournament'}
          </button>
        </form>
        <ErrorNote error={failed ?? picker.error ?? createTournament.error} />
      </Card>
    </Page>
  );
}
