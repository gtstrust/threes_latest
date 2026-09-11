/**
 * The draw: every group, who is in it, and which loop they play.
 *
 * Groups tee off at once on different loops. How many can do that is the event's
 * start style (ADR-011): a shotgun makes every hole in play a starting tee, so a
 * full course carries eighteen groups, while blocks cut disjoint triples and
 * carry six. Past whichever ceiling applies, groups share a loop and tee off
 * staggered — that is expected, not an error, so nothing here treats a repeated
 * loop as a problem.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';

import type {
  AdvancedBy,
  CourseWithHoles,
  Participant,
  RoundWithGroups,
  UUID,
} from '../../lib/types';
import { loopHoles, loopLabel } from './loop';

export function GroupList({
  round,
  field,
  myParticipantId,
  course,
  showAdvancement = false,
  onAdjudicate,
}: {
  round: RoundWithGroups;
  field: Participant[];
  myParticipantId?: UUID;
  course?: CourseWithHoles;
  /** Show who went through. Only a knockout has an answer (ADR-012). */
  showAdvancement?: boolean;
  /** Offered only to the organiser, and only for a group nothing separated. */
  onAdjudicate?: (groupId: UUID, participantId: UUID) => void;
}) {
  const nameOf = (id: UUID) => field.find((p) => p.id === id)?.display_name ?? 'Unknown';

  return (
    <ul className="list plain groups">
      {round.groups.map((group) => {
        const mine = myParticipantId
          ? group.members.some((member) => member.participant_id === myParticipantId)
          : false;
        const holes = loopLabel(loopHoles(group.holes, course));

        return (
          <li key={group.id} className={mine ? 'group mine' : 'group'}>
            <div className="group-head">
              <strong>Group {group.group_number}</strong>
              {holes && <span className="muted small">{holes}</span>}
              {mine && <span className="badge">You</span>}
            </div>
            <p className="muted">
              {group.members.map((member) => nameOf(member.participant_id)).join(' · ')}
            </p>
            {showAdvancement && group.advancing_participant_id && (
              <p className="muted small">
                Through: {nameOf(group.advancing_participant_id)}
                {group.advanced_by && ` (${reasonFor(group.advanced_by)})`}
              </p>
            )}
            {showAdvancement && !group.advancing_participant_id && onAdjudicate && (
              <Adjudicate
                group={group}
                nameOf={nameOf}
                onAdjudicate={onAdjudicate}
              />
            )}
            {mine && (
              <Link to={`/g/${group.id}`} className="button-link">
                Enter scores
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** How a player went through, in words rather than the stored label. */
function reasonFor(advancedBy: AdvancedBy): string {
  return {
    points: 'on points',
    strokes: 'on fewest strokes',
    countback: 'on countback',
    organiser: 'your call',
  }[advancedBy];
}

/**
 * The organiser's answer for a group nothing could separate.
 *
 * Only ever rendered for an all-square group — everyone level on points and
 * strokes with no hole won by anyone — because that is the only case the ADR-012
 * cascade leaves open. The next round cannot be drawn until this is answered, so
 * it says so rather than sitting there as an unexplained dropdown.
 */
function Adjudicate({
  group,
  nameOf,
  onAdjudicate,
}: {
  group: RoundWithGroups['groups'][number];
  nameOf: (id: UUID) => string;
  onAdjudicate: (groupId: UUID, participantId: UUID) => void;
}) {
  const [chosen, setChosen] = useState<UUID>(group.members[0]?.participant_id ?? '');

  return (
    <div className="adjudicate">
      <p className="muted small">
        Nothing separated this group — level on points and strokes, and no hole won later.
        Pick who goes through before drawing the next round.
      </p>
      <label htmlFor={`through-${group.id}`}>Goes through</label>
      <select
        id={`through-${group.id}`}
        value={chosen}
        onChange={(event) => setChosen(event.target.value)}
      >
        {group.members.map((member) => (
          <option key={member.participant_id} value={member.participant_id}>
            {nameOf(member.participant_id)}
          </option>
        ))}
      </select>
      <button type="button" onClick={() => onAdjudicate(group.id, chosen)} disabled={!chosen}>
        Send this player through
      </button>
    </div>
  );
}
