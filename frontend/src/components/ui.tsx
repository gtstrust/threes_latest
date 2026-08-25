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

export function Page({
  title,
  back,
  children,
  actions,
}: {
  title: string;
  back?: { to: string; label: string };
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <main>
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

export function Card({ children }: { children: ReactNode }) {
  return <section className="card">{children}</section>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted empty">{children}</p>;
}
