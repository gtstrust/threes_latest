/**
 * The draw: every group, who is in it, and which loop they play.
 *
 * A shotgun start, so all groups tee off at once on different loops. Above 18
 * players groups share loops and tee off staggered — that is expected, not an
 * error, so nothing here treats a repeated loop as a problem.
 */

import { Link } from 'react-router-dom';

import type { CourseWithHoles, Participant, RoundWithGroups, UUID } from '../../lib/types';

export function GroupList({
  round,
  field,
  myParticipantId,
  course,
}: {
  round: RoundWithGroups;
  field: Participant[];
  myParticipantId?: UUID;
  course?: CourseWithHoles;
}) {
  const nameOf = (id: UUID) => field.find((p) => p.id === id)?.display_name ?? 'Unknown';

  // Hole *numbers* are what a golfer recognises; the API deals in hole ids.
  const numberOf = (holeId: UUID) =>
    course?.holes.find((hole) => hole.id === holeId)?.hole_number;

  return (
    <ul className="list plain groups">
      {round.groups.map((group) => {
        const mine = myParticipantId
          ? group.members.some((member) => member.participant_id === myParticipantId)
          : false;
        const loop = [...group.holes]
          .sort((a, b) => a.sequence - b.sequence)
          .map((hole) => numberOf(hole.hole_id))
          .filter((n): n is number => n !== undefined);

        return (
          <li key={group.id} className={mine ? 'group mine' : 'group'}>
            <div className="group-head">
              <strong>Group {group.group_number}</strong>
              {loop.length > 0 && <span className="muted small">Holes {loop.join(', ')}</span>}
              {mine && <span className="badge">You</span>}
            </div>
            <p className="muted">
              {group.members.map((member) => nameOf(member.participant_id)).join(' · ')}
            </p>
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
