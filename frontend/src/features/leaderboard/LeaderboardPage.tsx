/**
 * The board, and the client half of ADR-010.
 *
 * The realtime ping says only that something moved. This screen answers it by
 * **invalidating the query** — never by rendering the payload, which carries no
 * scores precisely so that nobody is tempted to. Refetching goes back through
 * FastAPI, where `require_can_view` decides what this caller may see; rendering
 * from the message would be a second read path with no such guard.
 *
 * Nothing here is recomputed. Positions repeat and skip (1, 2, 2, 4) as golf
 * expects, level players are already ordered by fewest strokes, and
 * `holes_played` shows who is still out on the course — all decided server-side
 * (ADR-002) and taken as given.
 */

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { HelpPanel } from '../help/HelpPanel';
import { reachedLabel } from '../tournaments/knockout';
import { keys, useLeaderboard, useRoundLeaderboard, useRounds } from '../../lib/queries';
import { subscribeToTournament } from '../../lib/realtime';
import type { Leaderboard, UUID } from '../../lib/types';

export function LeaderboardPage({ tournamentId }: { tournamentId: UUID }) {
  const client = useQueryClient();
  const rounds = useRounds(tournamentId);
  const [roundId, setRoundId] = useState<UUID | 'all'>('all');
  const [live, setLive] = useState(false);

  const overall = useLeaderboard(tournamentId);
  const perRound = useRoundLeaderboard(roundId === 'all' ? undefined : roundId);

  useEffect(() => {
    const unsubscribe = subscribeToTournament(tournamentId, () => {
      setLive(true);
      // Invalidate the whole tournament subtree: a scored hole moves the
      // cumulative board, the round board, and the group's card at once, and
      // guessing which one the viewer is looking at would just be a way to miss.
      void client.invalidateQueries({ queryKey: ['tournament', tournamentId] });
      void client.invalidateQueries({ queryKey: keys.roundLeaderboard(roundId as UUID) });
    });
    return unsubscribe;
  }, [tournamentId, client, roundId]);

  const board = roundId === 'all' ? overall : perRound;

  return (
    <Page
      title="Leaderboard"
      back={{ to: `/t/${tournamentId}`, label: 'Tournament' }}
      actions={
        live ? (
          // Was a muted line of text under the tabs, which is where nobody
          // looks. As a pill beside the heading it says the same thing where
          // the eye already is.
          <span className="badge live" aria-live="polite">
            Live
          </span>
        ) : undefined
      }
    >
      <HelpPanel topic="board" />

      {rounds.data && rounds.data.length > 0 && (
        <nav className="switcher" aria-label="Which board">
          <button
            type="button"
            className={roundId === 'all' ? 'tab current' : 'tab'}
            onClick={() => setRoundId('all')}
          >
            Overall
          </button>
          {rounds.data.map((round) => (
            <button
              key={round.id}
              type="button"
              className={roundId === round.id ? 'tab current' : 'tab'}
              onClick={() => setRoundId(round.id)}
            >
              R{round.round_number}
            </button>
          ))}
        </nav>
      )}

      {board.isPending && <Loading what="Loading the board" />}
      <ErrorNote error={board.error} />
      {board.data && <Board board={board.data} />}
    </Page>
  );
}

export function Board({ board }: { board: Leaderboard }) {
  if (board.entries.length === 0) {
    return (
      <Card>
        <Empty>No scores yet.</Empty>
      </Card>
    );
  }

  // A knockout board carries how far each player got, and is ranked by it first
  // (ADR-012). A round-robin board carries null and is ranked exactly as it
  // always was, so the column is absent rather than empty.
  // `!= null` rather than `!== null`: an older client or a trimmed payload can
  // leave the key absent, and undefined means the same thing here — this board
  // is not a knockout's, so the column does not belong on it.
  const knockout = board.entries.some((entry) => entry.rounds_survived != null);
  // Same shape, same reasoning (ADR-013): a scratch event sends null for every
  // player, so the column is absent rather than a row of numbers repeating the
  // one beside it. It is a property of the event, so any entry carrying one
  // means the whole board has one.
  const handicapped = board.entries.some((entry) => entry.net_strokes != null);
  const roundsPlayed = Math.max(
    0,
    ...board.entries.map((entry) => entry.rounds_survived ?? 0),
  ) - 1;

  return (
    <Card>
      <table className="board">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Player</th>
            {knockout && <th scope="col">Reached</th>}
            <th scope="col">Pts</th>
            <th scope="col">Strokes</th>
            {handicapped && <th scope="col">Net</th>}
            <th scope="col">Holes</th>
          </tr>
        </thead>
        <tbody>
          {board.entries.map((entry) => (
            <tr key={entry.participant_id}>
              {/* Weight by placing, so the shape of the board reads without
                  being read: the leader in the accent, the podium in ink, the
                  rest muted. */}
              <td className={`place place-${Math.min(entry.position, 4)}`}>{entry.position}</td>
              <td>{entry.display_name}</td>
              {knockout && (
                <td className="muted">{reachedLabel(entry.rounds_survived, roundsPlayed)}</td>
              )}
              <td>
                <strong>{entry.points}</strong>
              </td>
              <td className="muted">{entry.total_strokes}</td>
              {/* Net is what the board was ranked on, so it carries the weight
                  and gross sits muted beside it — the opposite emphasis to the
                  scorecard, where the group's own number is the subject. */}
              {handicapped && (
                <td>
                  <strong>{entry.net_strokes}</strong>
                </td>
              )}
              {/* Everyone drawn is listed, on nothing until they score — a board
                  missing half the field early in the day reads as a bug. */}
              <td className="muted">{entry.holes_played}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        {knockout
          ? `Ranked by how far a player got, then points, then fewest ${
              handicapped ? 'net strokes' : 'total strokes'
            }.`
          : `Level players are split by fewest ${
              handicapped ? 'net strokes — gross less the shots received' : 'total strokes'
            }.`}
      </p>
    </Card>
  );
}
