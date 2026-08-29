/**
 * The whole card at a glance: every player against every hole they played.
 *
 * Score entry is one hole at a time, which is right on a green and useless
 * afterwards. This is what people want when the round is over and what an
 * organiser reads to settle an argument — so it shows not just the strokes but
 * *how* each hole was decided, which is the thing a dispute is actually about.
 *
 * Read-only by construction. Corrections go back through score entry, which is
 * the single upsert path ADR-009 keeps both tables consistent through.
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { api } from '../../lib/api';
import { useCourse, useGroupCard, useRound, useTournament } from '../../lib/queries';
import type { DecidedBy, Group, HoleResult, Participant, UUID } from '../../lib/types';

/** ADR-007's three levels, said the way a player would say them. */
const HOW: Record<DecidedBy, string> = {
  strokes: 'fewest strokes',
  closest_to_pin: 'closest to the pin',
  longest_drive: 'longest drive on the fairway',
  no_winner: 'nobody could be separated',
};

type BackTo = { to: string; label: string };

export function ScorecardPage({ groupId, backTo }: { groupId: UUID; backTo?: BackTo }) {
  const group = useQuery({
    queryKey: ['group', groupId],
    queryFn: () => api.get<Group>(`/groups/${groupId}`),
  });
  const round = useRound(group.data?.round_id);
  const card = useGroupCard(groupId);
  const tournamentId = round.data?.tournament_id;

  const field = useQuery({
    queryKey: ['tournament', tournamentId, 'participants'],
    queryFn: () => api.get<Participant[]>(`/tournaments/${tournamentId}/participants`),
    enabled: Boolean(tournamentId),
  });
  // For the real hole numbers. A group plays holes 4-6 of a course, and "4" is
  // what a player recognises — "hole 1 of the loop" is the app's bookkeeping,
  // not theirs.
  const tournament = useTournament(tournamentId ?? '');
  const course = useCourse(tournament.data?.course_id);

  const back = backTo ?? { to: `/g/${groupId}`, label: 'Scoring' };

  if (group.isPending || round.isPending || card.isPending || field.isPending)
    return <Loading what="Loading the card" />;

  if (group.error || round.error || card.error || field.error)
    return (
      <Page title="Scorecard" back={back}>
        <ErrorNote error={group.error ?? round.error ?? card.error ?? field.error} />
      </Page>
    );

  const loop = [...(group.data?.holes ?? [])].sort((a, b) => a.sequence - b.sequence);
  const played = card.data?.holes ?? [];
  const members = group.data?.members.map((m) => m.participant_id) ?? [];
  const nameOf = (id: UUID) => field.data?.find((p) => p.id === id)?.display_name ?? 'Player';

  // Ordered by the loop, not by what happened to be scored first — a card reads
  // in playing order or it isn't a card. The label is the course's own hole
  // number where it is known, falling back to the position in the loop while
  // the course is still loading.
  const numberOf = new Map(course.data?.holes.map((h) => [h.id, h.hole_number]) ?? []);
  const holes = loop.map((hole, index) => ({
    key: hole.hole_id,
    label: numberOf.get(hole.hole_id) ?? index + 1,
    result: played.find((r) => r.hole_id === hole.hole_id) ?? null,
  }));

  return (
    <Page title="Scorecard" back={back}>
      <p className="muted small">
        Group {group.data?.group_number} · {played.length} of {loop.length} holes scored
      </p>

      {played.length === 0 ? (
        <Card>
          <Empty>Nothing scored yet. The card fills in as the group plays.</Empty>
        </Card>
      ) : (
        <>
          <Card>
            <table className="board card-grid">
              <thead>
                <tr>
                  <th scope="col">Player</th>
                  {holes.map((hole) => (
                    <th scope="col" key={hole.key}>
                      {hole.label}
                    </th>
                  ))}
                  <th scope="col">Pts</th>
                </tr>
              </thead>
              <tbody>
                {members.map((id) => (
                  <tr key={id}>
                    <td>{nameOf(id)}</td>
                    {holes.map((hole) => {
                      const score = hole.result?.scores.find((s) => s.participant_id === id);
                      const won = hole.result?.winner_participant_id === id;
                      return (
                        <td key={hole.key}>
                          <span className={won ? 'took' : undefined}>{score?.strokes ?? '—'}</span>
                        </td>
                      );
                    })}
                    <td>{totalPoints(played, id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">A ring marks the hole that player took.</p>
          </Card>

          <Card>
            <h2>How each hole went</h2>
            <ul className="list plain">
              {holes.map((hole) => (
                <li key={hole.key}>
                  <span>Hole {hole.label}</span>
                  <span className="muted">{describe(hole.result, nameOf)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}

      <Link to={back.to} className="button-link">
        Back to scoring
      </Link>
    </Page>
  );
}

function totalPoints(played: HoleResult[], participantId: UUID): number {
  return played.reduce(
    (sum, hole) => sum + (hole.scores.find((s) => s.participant_id === participantId)?.points ?? 0),
    0,
  );
}

/**
 * One line per hole. A halved hole is stated plainly rather than shown as a
 * blank or an error: holes are never halved into shared points (ADR-007), so
 * "nobody won it" is a real outcome the card has to be able to say.
 */
function describe(result: HoleResult | null, nameOf: (id: UUID) => string): string {
  if (!result) return 'Not played yet';
  if (!result.winner_participant_id) return 'Nobody won it';
  return `${nameOf(result.winner_participant_id)} — ${HOW[result.decided_by]}`;
}
