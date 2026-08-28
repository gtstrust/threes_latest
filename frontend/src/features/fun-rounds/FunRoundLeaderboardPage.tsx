/**
 * A fun round's board — one round, so no Overall/round tabs, but the same
 * ADR-010 discipline as the tournament board: the realtime ping only invalidates
 * the query; the refetch goes back through FastAPI. Nothing is rendered from the
 * message.
 */

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { Board } from '../leaderboard/LeaderboardPage';
import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { keys, useFunRound, useRoundLeaderboard } from '../../lib/queries';
import { subscribeToTournament } from '../../lib/realtime';
import type { UUID } from '../../lib/types';

export function FunRoundLeaderboardPage({ funRoundId }: { funRoundId: UUID }) {
  const client = useQueryClient();
  const funRound = useFunRound(funRoundId);
  const [live, setLive] = useState(false);

  const roundId = funRound.data?.round?.id;
  const board = useRoundLeaderboard(roundId);

  useEffect(() => {
    // The signal is broadcast on the tournament topic, and a fun round is a
    // tournament underneath — so its id is the topic id.
    const unsubscribe = subscribeToTournament(funRoundId, () => {
      setLive(true);
      if (roundId) void client.invalidateQueries({ queryKey: keys.roundLeaderboard(roundId) });
    });
    return unsubscribe;
  }, [funRoundId, roundId, client]);

  return (
    <Page title="Leaderboard" back={{ to: `/r/${funRoundId}`, label: 'Fun round' }}>
      {live && (
        <p className="muted small" aria-live="polite">
          Updating live
        </p>
      )}

      {funRound.isPending && <Loading what="Loading the round" />}
      <ErrorNote error={funRound.error} />

      {funRound.data && !roundId && (
        <Card>
          <Empty>The round hasn&rsquo;t started yet.</Empty>
        </Card>
      )}

      {board.isPending && roundId && <Loading what="Loading the board" />}
      <ErrorNote error={board.error} />
      {board.data && <Board board={board.data} />}
    </Page>
  );
}
