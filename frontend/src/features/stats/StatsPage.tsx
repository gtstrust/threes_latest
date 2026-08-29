/**
 * Your own record: what you've played, and how it's gone.
 *
 * Deliberately four numbers and a list. The interesting one is strokes per hole,
 * because it is the only figure here that moves as somebody actually improves —
 * holes won depends as much on who you drew as on how you played.
 *
 * Every number is computed server-side (ADR-002's reasoning about scores applies
 * to the arithmetic about them too), so this file does no maths beyond
 * formatting.
 */

import { Link } from 'react-router-dom';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { useMyCourseRecords, useMyStats } from '../../lib/queries';
import { useSession } from '../auth/session-context';
import type { Career, CourseRecord, HistoryEntry } from '../../lib/types';

export function StatsPage() {
  const { player } = useSession();
  const stats = useMyStats();

  if (stats.isPending) return <Loading what="Loading your record" />;
  if (stats.error || !stats.data)
    return (
      <Page title="Your golf" back={{ to: '/', label: 'Home' }}>
        <ErrorNote error={stats.error} />
      </Page>
    );

  const { career, history } = stats.data;

  return (
    <Page title="Your golf" back={{ to: '/', label: 'Home' }}>
      <p className="muted">{player?.display_name ?? player?.email}</p>

      <Card>
        <h2>Career</h2>
        {career.holes_played === 0 ? (
          <Empty>Nothing scored yet. Your numbers show up after your first hole.</Empty>
        ) : (
          <CareerGrid career={career} />
        )}
      </Card>

      <CourseRecords />

      <Card>
        <h2>Round by round</h2>
        {history.length === 0 ? (
          <Empty>No rounds yet.</Empty>
        ) : (
          <ul className="list plain">
            {history.map((entry) => (
              <HistoryRow key={entry.tournament_id} entry={entry} />
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}

/**
 * Where you've played, and how each hole has treated you.
 *
 * Only interesting once somebody has been round a course more than once, which
 * is why the visit count leads each block — a single round's "average" is just
 * that round, and saying so stops the number reading as more than it is.
 */
function CourseRecords() {
  const courses = useMyCourseRecords();

  if (courses.isPending) return null;
  if (courses.error)
    return (
      <Card>
        <h2>By course</h2>
        <ErrorNote error={courses.error} />
      </Card>
    );
  if (!courses.data?.length) return null;

  return (
    <Card>
      <h2>By course</h2>
      {courses.data.map((course) => (
        <CourseBlock key={course.course_id} course={course} />
      ))}
    </Card>
  );
}

function CourseBlock({ course }: { course: CourseRecord }) {
  return (
    <section className="course-record">
      <h3>
        {course.course_name}{' '}
        <span className="muted small">
          {course.rounds_played} {course.rounds_played === 1 ? 'round' : 'rounds'} ·{' '}
          {course.average_strokes.toFixed(2)} per hole
        </span>
      </h3>
      <table className="board">
        <thead>
          <tr>
            <th>Hole</th>
            <th>Played</th>
            <th>Avg</th>
            <th>Best</th>
            <th>Won</th>
          </tr>
        </thead>
        <tbody>
          {course.holes.map((hole) => (
            <tr key={hole.hole_number}>
              <td>{hole.hole_number}</td>
              <td>{hole.times_played}</td>
              <td>{hole.average_strokes.toFixed(2)}</td>
              <td>{hole.best_strokes}</td>
              <td>
                {hole.holes_won}/{hole.times_played}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CareerGrid({ career }: { career: Career }) {
  const figures: [string, string][] = [
    ['Rounds played', String(career.events_played)],
    ['Holes played', String(career.holes_played)],
    ['Holes won', String(career.holes_won)],
    // Rounded server-side; shown as a percentage because a share of holes reads
    // more naturally than 0.417.
    ['Win rate', `${Math.round(career.win_rate * 100)}%`],
    ['Strokes per hole', career.average_strokes.toFixed(2)],
    ['Total strokes', String(career.total_strokes)],
  ];

  return (
    <dl className="figures">
      {figures.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function HistoryRow({ entry }: { entry: HistoryEntry }) {
  const where =
    entry.kind === 'FUN_ROUND' ? `/r/${entry.tournament_id}` : `/t/${entry.tournament_id}`;

  return (
    <li>
      <Link to={where}>
        <span className="list-name">{entry.name}</span>
        <span className="muted">
          {entry.position === null
            ? 'Not played yet'
            : `${ordinal(entry.position)} · ${entry.points} pt · ${entry.total_strokes} strokes`}
        </span>
      </Link>
    </li>
  );
}

/** 1st, 2nd, 3rd — including the 11th/12th/13th exceptions. */
function ordinal(position: number): string {
  const tens = position % 100;
  if (tens >= 11 && tens <= 13) return `${position}th`;
  return `${position}${['th', 'st', 'nd', 'rd'][position % 10] ?? 'th'}`;
}
