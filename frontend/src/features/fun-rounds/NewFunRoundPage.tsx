/**
 * Starting a fun round: name it, pick or create a course, and you're the host in
 * a lobby your mates can join by link.
 *
 * The course defaults to three holes — a fun round is a single 3-hole loop — but
 * a bigger course works too; the three holes get chosen at the start step.
 */

import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { Card, ErrorNote, Page } from '../../components/ui';
import { useCoursePicker } from '../courses/CoursePicker';
import { useCreateFunRound } from '../../lib/queries';

export function NewFunRoundPage() {
  const navigate = useNavigate();
  const picker = useCoursePicker({ defaultHoles: 3 });
  const createFunRound = useCreateFunRound();

  const [name, setName] = useState('');

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const chosen = await picker.resolveCourseId();
    const funRound = await createFunRound.mutateAsync({
      name,
      ...(chosen ? { course_id: chosen } : {}),
    });
    void navigate(`/r/${funRound.id}`);
  }

  const busy = picker.busy || createFunRound.isPending;

  return (
    <Page title="New fun round" back={{ to: '/', label: 'Home' }}>
      <Card>
        <form onSubmit={onSubmit}>
          <label htmlFor="name">What are you playing?</label>
          <input
            id="name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Saturday nine"
          />

          {picker.element}

          <button type="submit" disabled={busy || !name}>
            {busy ? 'Starting…' : 'Start a fun round'}
          </button>
        </form>
        <ErrorNote error={picker.error ?? createFunRound.error} />
      </Card>
    </Page>
  );
}
