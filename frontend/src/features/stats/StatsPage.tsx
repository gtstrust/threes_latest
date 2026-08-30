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

import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { useMyCourseRecords, useMyStats, useUpdateProfile } from '../../lib/queries';
import { useSession } from '../auth/session-context';
import { ReferralCard } from '../referrals/ReferralCard';
import {
  applyTheme,
  readPreference,
  setPreference,
  watchSystemTheme,
  type ThemePreference,
} from '../../lib/theme';
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
      <p className="muted">{player?.email}</p>

      <DisplayName />

      <Appearance />

      <ReferralCard />

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
/**
 * Your name as everyone else sees it.
 *
 * Without one, `display_name` falls back to the email address — so a corporate
 * day's leaderboard prints `firstname.lastname@company.com` down the page,
 * which is both ugly and a small privacy leak to the rest of the field.
 */
function DisplayName() {
  const { player, retryProfile } = useSession();
  const update = useUpdateProfile();
  const [name, setName] = useState(player?.display_name ?? '');

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    // The session holds its own copy of the player and nothing in the query
    // cache can reach it, so the refresh has to be asked for explicitly —
    // otherwise the header still shows the old name over the new form.
    update.mutate({ display_name: name.trim() }, { onSuccess: () => retryProfile() });
  }

  return (
    <Card>
      <h2>Your name</h2>
      <form onSubmit={onSubmit}>
        <label htmlFor="display-name">Display name</label>
        <input
          id="display-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Kim Nguyen"
        />
        <p className="muted small">
          This is the name on leaderboards. Without it, your email address shows instead.
        </p>
        <button type="submit" disabled={update.isPending || !name.trim()}>
          {update.isPending ? 'Saving…' : 'Save'}
        </button>
      </form>
      <ErrorNote error={update.error} />
    </Card>
  );
}

/** What each choice actually does, said plainly — "System" is not obvious. */
const APPEARANCE: { value: ThemePreference; label: string; note: string }[] = [
  {
    value: 'system',
    label: 'System',
    note: 'Follows your phone. Scoring stays bright, so it stays readable in sun.',
  },
  { value: 'light', label: 'Light', note: 'Bright everywhere. Best outdoors.' },
  { value: 'dark', label: 'Dark', note: 'Dark everywhere, scoring included.' },
];

/**
 * Which theme the app wears.
 *
 * Plain radios rather than a custom control: they work with a thumb, with a
 * screen reader, and with the keyboard, none of which we would get for free
 * otherwise. The same reasoning the login form uses for plain inputs.
 */
function Appearance() {
  const [preference, setChoice] = useState<ThemePreference>(readPreference);

  // Only matters while "System" is selected — a phone that flips to dark at
  // sunset should take the app with it rather than waiting for a reload that,
  // on a PWA left open in a cart, may never come.
  useEffect(() => {
    if (preference !== 'system') return;
    return watchSystemTheme(() => applyTheme('system'));
  }, [preference]);

  function choose(next: ThemePreference) {
    setChoice(next);
    setPreference(next);
  }

  return (
    <Card>
      <h2>Appearance</h2>
      <fieldset className="choices-list">
        <legend className="visually-hidden">Appearance</legend>
        {APPEARANCE.map((option) => (
          <label key={option.value} className="choice">
            <input
              type="radio"
              name="appearance"
              value={option.value}
              checked={preference === option.value}
              onChange={() => choose(option.value)}
            />
            <span>
              <span className="list-name">{option.label}</span>
              <span className="muted small"> {option.note}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </Card>
  );
}

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
