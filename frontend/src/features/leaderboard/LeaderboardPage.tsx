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
    <Page title="Leaderboard" back={{ to: `/t/${tournamentId}`, label: 'Tournament' }}>
      {rounds.data && rounds.data.length > 0 && (
        <nav className="hole-tabs" aria-label="Which board">
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

      {live && (
        <p className="muted small" aria-live="polite">
          Updating live
        </p>
      )}

      {board.isPending && <Loading what="Loading the board" />}
      <ErrorNote error={board.error} />
      {board.data && <Board board={board.data} />}
    </Page>
  );
}

function Board({ board }: { board: Leaderboard }) {
  if (board.entries.length === 0) {
    return (
      <Card>
        <Empty>No scores yet.</Empty>
      </Card>
    );
  }

  return (
    <Card>
      <table className="board">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Player</th>
            <th scope="col">Pts</th>
            <th scope="col">Strokes</th>
            <th scope="col">Holes</th>
          </tr>
        </thead>
        <tbody>
          {board.entries.map((entry) => (
            <tr key={entry.participant_id}>
              <td>{entry.position}</td>
              <td>{entry.display_name}</td>
              <td>
                <strong>{entry.points}</strong>
              </td>
              <td className="muted">{entry.total_strokes}</td>
              {/* Everyone drawn is listed, on nothing until they score — a board
                  missing half the field early in the day reads as a bug. */}
              <td className="muted">{entry.holes_played}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">Level players are split by fewest total strokes.</p>
    </Card>
  );
}
