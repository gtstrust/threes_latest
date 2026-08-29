/**
 * Entering a group's card, one hole at a time.
 *
 * The screen a player uses most, standing on a green with one hand free. So:
 * big number steppers rather than a keyboard, one hole at a time rather than a
 * grid, and the tie-break asked as a question with faces to tap.
 *
 * The cascade itself lives in `cascade.ts`, pure and tested. This file is the
 * conversation around it — which is genuinely a conversation, not a form: the
 * strokes go in, and only if they tie does the app ask who was closest to the
 * pin, and only of the players who actually tied.
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Card, ErrorNote, Loading, Page } from '../../components/ui';
import { useGroupCard, useRound, useSubmitHole } from '../../lib/queries';
import { api } from '../../lib/api';
import { useQuery } from '@tanstack/react-query';
import type { Group, HoleResult, Participant, Round, UUID } from '../../lib/types';
import { NOTHING_ASKED, nextPrompt, strokesFrom, type Asked } from './cascade';

/**
 * Where the whole card lives for this group.
 *
 * A fun round nests its group under the round (`/r/:id/g/:groupId`) so the back
 * link can lead somewhere sensible; a tournament's is top level. The card
 * follows whichever shape brought us here.
 */
function cardPath(groupId: UUID, backTo?: BackTo): string {
  return backTo?.to.startsWith('/r/') ? `${backTo.to}/g/${groupId}/card` : `/g/${groupId}/card`;
}

/** A sane opening guess, so most holes are two taps rather than four. */
const DEFAULT_STROKES = 4;

/**
 * Where "back" goes and what it's called. Defaults to the tournament this group
 * belongs to; a fun round passes its own page instead, since the same scoring
 * screen serves both.
 */
type BackTo = { to: string; label: string };

export function ScorePage({ groupId, backTo }: { groupId: UUID; backTo?: BackTo }) {
  const group = useQuery({
    queryKey: ['group', groupId],
    queryFn: () => api.get<Group>(`/groups/${groupId}`),
  });
  const round = useRound(group.data?.round_id);
  const card = useGroupCard(groupId);

  if (group.isPending || round.isPending) return <Loading what="Loading your group" />;
  if (group.error || round.error)
    return (
      <Page title="Scores" back={backTo ?? { to: '/', label: 'Home' }}>
        <ErrorNote error={group.error ?? round.error} />
      </Page>
    );

  return (
    <ScoreCard
      group={group.data!}
      round={round.data!}
      played={card.data?.holes ?? []}
      loading={card.isPending}
      backTo={backTo}
    />
  );
}

function ScoreCard({
  group,
  round,
  played,
  loading,
  backTo,
}: {
  group: Group;
  round: Round & { groups: Group[] };
  played: HoleResult[];
  loading: boolean;
  backTo?: BackTo;
}) {
  const tournamentId = round.tournament_id;
  const field = useQuery({
    queryKey: ['tournament', tournamentId, 'participants'],
    queryFn: () => api.get<Participant[]>(`/tournaments/${tournamentId}/participants`),
  });

  const loop = useMemo(
    () => [...group.holes].sort((a, b) => a.sequence - b.sequence),
    [group.holes],
  );

  const scoredIds = new Set(played.map((hole) => hole.hole_id));
  const firstUnplayed = loop.find((hole) => !scoredIds.has(hole.hole_id)) ?? loop[0];
  const [holeId, setHoleId] = useState<UUID>(firstUnplayed?.hole_id ?? '');

  const existing = played.find((hole) => hole.hole_id === holeId);
  const nameOf = (id: UUID) => field.data?.find((p) => p.id === id)?.display_name ?? 'Player';

  if (field.isPending || loading) return <Loading what="Loading the card" />;

  return (
    <Page
      title={`Group ${group.group_number}`}
      back={backTo ?? { to: `/t/${tournamentId}`, label: 'Tournament' }}
    >
      <nav className="hole-tabs" aria-label="Holes in this loop">
        {loop.map((hole, index) => (
          <button
            key={hole.hole_id}
            type="button"
            className={hole.hole_id === holeId ? 'tab current' : 'tab'}
            aria-current={hole.hole_id === holeId}
            onClick={() => setHoleId(hole.hole_id)}
          >
            {index + 1}
            {scoredIds.has(hole.hole_id) && <span aria-label="scored"> ✓</span>}
          </button>
        ))}
      </nav>

      <Link to={cardPath(group.id, backTo)} className="button-link">
        See the whole card
      </Link>

      {holeId && (
        <HoleEntry
          key={holeId}
          groupId={group.id}
          tournamentId={tournamentId}
          holeId={holeId}
          members={group.members.map((member) => member.participant_id)}
          nameOf={nameOf}
          existing={existing}
        />
      )}
    </Page>
  );
}

function HoleEntry({
  groupId,
  tournamentId,
  holeId,
  members,
  nameOf,
  existing,
}: {
  groupId: UUID;
  tournamentId: UUID;
  holeId: UUID;
  members: UUID[];
  nameOf: (id: UUID) => string;
  existing?: HoleResult;
}) {
  const submit = useSubmitHole(groupId, tournamentId);

  const [strokes, setStrokes] = useState<Record<UUID, number>>(() =>
    existing
      ? strokesFrom(existing)
      : Object.fromEntries(members.map((id) => [id, DEFAULT_STROKES])),
  );

  // What the group has already been *asked*, which the response cannot tell us:
  // a pin answer that names a tied player always decides the hole, so reaching
  // longest drive means the group declined the pin question — and declining
  // sends nothing. See cascade.ts.
  const [asked, setAsked] = useState<Asked>(NOTHING_ASKED);

  const latest = submit.data ?? existing;
  const prompt = latest ? nextPrompt(latest, asked) : null;

  function post(answer?: { closest_to_pin?: UUID; longest_drive?: UUID }) {
    submit.mutate({ holeId, strokes, ...answer });
  }

  return (
    <>
      <Card>
        <h2>Strokes</h2>
        {members.map((id) => (
          <div className="stroke-row" key={id}>
            <span className="stroke-name">{nameOf(id)}</span>
            <div className="stepper">
              <button
                type="button"
                aria-label={`One fewer for ${nameOf(id)}`}
                onClick={() =>
                  setStrokes((prev) => ({ ...prev, [id]: Math.max(1, (prev[id] ?? 1) - 1) }))
                }
              >
                −
              </button>
              <output aria-label={`Strokes for ${nameOf(id)}`}>{strokes[id]}</output>
              <button
                type="button"
                aria-label={`One more for ${nameOf(id)}`}
                onClick={() => setStrokes((prev) => ({ ...prev, [id]: (prev[id] ?? 0) + 1 }))}
              >
                +
              </button>
            </div>
          </div>
        ))}
        <button
          type="button"
          onClick={() => {
            setAsked(NOTHING_ASKED);
            post();
          }}
          disabled={submit.isPending}
        >
          {submit.isPending ? 'Saving…' : existing ? 'Update this hole' : 'Save hole'}
        </button>
        <ErrorNote error={submit.error} />
      </Card>

      {prompt?.kind === 'ask_closest_to_pin' && (
        <TieBreak
          question="Who was closest to the pin?"
          note="Only these players tied, so only they can win the hole."
          candidates={prompt.candidates}
          nameOf={nameOf}
          onPick={(id) => post({ closest_to_pin: id })}
          onDecline={() => setAsked((prev) => ({ ...prev, closestToPin: true }))}
          declineLabel="Nobody reached the green"
          busy={submit.isPending}
        />
      )}

      {prompt?.kind === 'ask_longest_drive' && (
        <TieBreak
          question="Who hit the longest drive on the fairway?"
          note="A drive that finished in the rough doesn't count, however long."
          candidates={prompt.candidates}
          nameOf={nameOf}
          onPick={(id) => post({ longest_drive: id })}
          onDecline={() => setAsked((prev) => ({ ...prev, longestDrive: true }))}
          declineLabel="Nobody found the fairway"
          busy={submit.isPending}
        />
      )}

      {prompt?.kind === 'nobody_wins' && (
        <Card>
          <h2>Nobody wins this hole</h2>
          {/* Holes are never halved (ADR-007), so the alternative to one winner
              is none — not a share. Everyone scores zero and the hole stands. */}
          <p className="muted">
            {prompt.candidates.map(nameOf).join(' and ')} couldn&rsquo;t be separated. Everyone
            scores zero for it.
          </p>
        </Card>
      )}

      {prompt?.kind === 'settled' && <Settled result={prompt.result} nameOf={nameOf} />}
    </>
  );
}

function TieBreak({
  question,
  note,
  candidates,
  nameOf,
  onPick,
  onDecline,
  declineLabel,
  busy,
}: {
  question: string;
  note: string;
  candidates: UUID[];
  nameOf: (id: UUID) => string;
  onPick: (id: UUID) => void;
  onDecline: () => void;
  declineLabel: string;
  busy: boolean;
}) {
  return (
    <Card>
      <h2>{question}</h2>
      <p className="muted small">{note}</p>
      <div className="choices">
        {candidates.map((id) => (
          <button key={id} type="button" onClick={() => onPick(id)} disabled={busy}>
            {nameOf(id)}
          </button>
        ))}
      </div>
      <button type="button" className="ghost" onClick={onDecline} disabled={busy}>
        {declineLabel}
      </button>
    </Card>
  );
}

function Settled({ result, nameOf }: { result: HoleResult; nameOf: (id: UUID) => string }) {
  const how = {
    strokes: 'fewest strokes',
    closest_to_pin: 'closest to the pin',
    longest_drive: 'longest drive on the fairway',
    no_winner: '',
  }[result.decided_by];

  return (
    <Card>
      <h2>Hole saved</h2>
      {result.winner_participant_id ? (
        <p>
          <strong>{nameOf(result.winner_participant_id)}</strong> takes it — {how}.
        </p>
      ) : (
        <p>Nobody won this hole.</p>
      )}
      <ul className="list plain">
        {result.scores.map((score) => (
          <li key={score.participant_id}>
            <span>{nameOf(score.participant_id)}</span>
            <span className="muted">
              {score.strokes} strokes · {score.points} pt
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
