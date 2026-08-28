/**
 * A course picked from the dropdown (rather than created fresh) might have
 * fewer than 3 holes entered — the bug in issue #16, where drawing a round
 * failed with "a loop needs 3 holes; the course has only 0 hole(s) entered"
 * and there was no way to fix it from the frontend.
 */

import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

const put = vi.fn().mockResolvedValue([]);
vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api');
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), put: (p: string, b: unknown) => put(p, b), delete: vi.fn() },
  };
});

const { CourseHolesEditor } = await import('./CourseHolesEditor');

function show(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('CourseHolesEditor', () => {
  it('flags a course with too few holes for a loop', () => {
    show(<CourseHolesEditor courseId="course-1" currentCount={0} />);

    expect(screen.getByText(/0 holes entered/i)).toBeInTheDocument();
    expect(screen.getByText(/a loop needs at least 3/i)).toBeInTheDocument();
  });

  it('appends holes past whatever already exists, leaving existing ones untouched', async () => {
    const user = userEvent.setup();
    show(<CourseHolesEditor courseId="course-1" currentCount={1} />);

    await user.click(screen.getByRole('button', { name: /add \d+ holes?/i }));

    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith('/courses/course-1/holes', {
      holes: [{ hole_number: 2 }, { hole_number: 3 }, { hole_number: 4 }],
    });
  });

  it('renders nothing once the course already has a full complement of holes', () => {
    const { container } = show(<CourseHolesEditor courseId="course-1" currentCount={18} />);

    expect(container).toBeEmptyDOMElement();
  });
});
