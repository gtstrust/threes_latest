/**
 * The handful of pieces every screen needs. Deliberately small — this is a
 * five-screen app, and a component library would be more code than the app.
 */

import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { ApiError } from '../lib/api';

export function Loading({ what = 'Loading' }: { what?: string }) {
  return <p className="muted">{what}…</p>;
}

/**
 * An error, phrased for whoever is standing on a tee holding the phone.
 *
 * FastAPI's `detail` is already written for a human — "A round can't be drawn
 * while the tournament is CREATED" — so it is shown as-is rather than replaced
 * with something generic. A 401 is the exception: "Not signed in" is true but
 * useless, since the app will already be showing the login screen.
 */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;

  const message =
    error instanceof ApiError
      ? error.detail
      : error instanceof Error
        ? error.message
        : 'Something went wrong.';

  return (
    <p role="alert" className="error">
      {message}
    </p>
  );
}

/**
 * A screen.
 *
 * `theme="lit"` opts into the high-luminance treatment — and it is a choice the
 * *screen* makes, not the phone. In direct sun a bright screen is more legible
 * than a dark one, so score entry and the scorecard ask for it whatever the
 * system preference says, while everything else keeps the dark brand register.
 */
export function Page({
  title,
  back,
  children,
  actions,
  theme,
}: {
  title: string;
  back?: { to: string; label: string };
  children: ReactNode;
  actions?: ReactNode;
  theme?: 'lit';
}) {
  return (
    <main className={theme}>
      {back && (
        <Link to={back.to} className="back">
          ← {back.label}
        </Link>
      )}
      <header className="page-header">
        <h1>{title}</h1>
        {actions}
      </header>
      {children}
    </main>
  );
}

/**
 * A card, optionally with a variant class.
 *
 * `className` rather than a `variant` enum: there is exactly one variant today
 * (`accent`, for the group card mid-round), and an enum for one value is a
 * vocabulary nobody needs yet.
 */
export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={className ? `card ${className}` : 'card'}>{children}</section>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted empty">{children}</p>;
}
