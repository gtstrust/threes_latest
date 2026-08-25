/**
 * Query keys and the hooks every feature shares.
 *
 * Keys live in one place because the realtime signal invalidates by prefix: a
 * ping for one tournament has to reach both leaderboards and the group cards
 * beneath it, and that only works if everyone agrees on the shape of the key.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './api';
import type {
  Course,
  CourseWithHoles,
  GroupCard,
  HoleResult,
  Leaderboard,
  Participant,
  Round,
  RoundWithGroups,
  Tournament,
  UUID,
} from './types';

export const keys = {
  organising: ['tournaments', 'organising'] as const,
  playing: ['tournaments', 'playing'] as const,
  /** Everything under one tournament, so a realtime ping can invalidate the lot. */
  tournament: (id: UUID) => ['tournament', id] as const,
  field: (id: UUID) => ['tournament', id, 'participants'] as const,
  rounds: (id: UUID) => ['tournament', id, 'rounds'] as const,
  leaderboard: (id: UUID) => ['tournament', id, 'leaderboard'] as const,
  roundLeaderboard: (roundId: UUID) => ['round', roundId, 'leaderboard'] as const,
  round: (roundId: UUID) => ['round', roundId] as const,
  card: (groupId: UUID) => ['group', groupId, 'card'] as const,
  courses: ['courses'] as const,
  course: (id: UUID) => ['course', id] as const,
};

// --- Tournaments -----------------------------------------------------------

/** What you run. Distinct from what you play — see `usePlaying`. */
export function useOrganising() {
  return useQuery({
    queryKey: keys.organising,
    queryFn: () => api.get<Tournament[]>('/tournaments'),
  });
}

/** What you play in, which you may not organise. */
export function usePlaying() {
  return useQuery({
    queryKey: keys.playing,
    queryFn: () => api.get<Tournament[]>('/players/me/tournaments'),
  });
}

export function useTournament(id: UUID) {
  return useQuery({
    queryKey: keys.tournament(id),
    queryFn: () => api.get<Tournament>(`/tournaments/${id}`),
  });
}

export function useField(id: UUID) {
  return useQuery({
    queryKey: keys.field(id),
    queryFn: () => api.get<Participant[]>(`/tournaments/${id}/participants`),
  });
}

export function useRounds(id: UUID) {
  return useQuery({
    queryKey: keys.rounds(id),
    queryFn: () => api.get<Round[]>(`/tournaments/${id}/rounds`),
  });
}

export function useRound(roundId: UUID | undefined) {
  return useQuery({
    queryKey: keys.round(roundId ?? 'none'),
    queryFn: () => api.get<RoundWithGroups>(`/rounds/${roundId}`),
    enabled: Boolean(roundId),
  });
}

export function useLeaderboard(id: UUID) {
  return useQuery({
    queryKey: keys.leaderboard(id),
    queryFn: () => api.get<Leaderboard>(`/tournaments/${id}/leaderboard`),
  });
}

export function useRoundLeaderboard(roundId: UUID | undefined) {
  return useQuery({
    queryKey: keys.roundLeaderboard(roundId ?? 'none'),
    queryFn: () => api.get<Leaderboard>(`/rounds/${roundId}/leaderboard`),
    enabled: Boolean(roundId),
  });
}

export function useCourses() {
  return useQuery({ queryKey: keys.courses, queryFn: () => api.get<Course[]>('/courses') });
}

export function useCourse(id: UUID | null | undefined) {
  return useQuery({
    queryKey: keys.course(id ?? 'none'),
    queryFn: () => api.get<CourseWithHoles>(`/courses/${id}`),
    enabled: Boolean(id),
  });
}

export function useGroupCard(groupId: UUID) {
  return useQuery({
    queryKey: keys.card(groupId),
    queryFn: () => api.get<GroupCard>(`/groups/${groupId}/scores`),
  });
}

// --- Mutations -------------------------------------------------------------

export function useCreateTournament() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; course_id?: UUID }) =>
      api.post<Tournament>('/tournaments', body),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.organising }),
  });
}

export function useSetStatus(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    // Only the registration transitions and the final one reach here. The play
    // statuses belong to the round endpoints (ADR-008) and this endpoint refuses
    // them, so the UI must never offer them.
    mutationFn: (status: string) =>
      api.post<Tournament>(`/tournaments/${id}/status`, { status }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tournament', id] }),
  });
}

export function useAddVirtualPlayer(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (display_name: string) =>
      api.post<Participant>(`/tournaments/${id}/participants/virtual`, { display_name }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.field(id) }),
  });
}

export function useJoinTournament(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Participant>(`/tournaments/${id}/participants`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.field(id) });
      void client.invalidateQueries({ queryKey: keys.playing });
    },
  });
}

export function useRemoveParticipant(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (participantId: UUID) =>
      api.delete<void>(`/tournaments/${id}/participants/${participantId}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.field(id) }),
  });
}

export function useDrawRound(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    // `hole_numbers` omitted means the whole course; a selection has to be a
    // multiple of three, since a loop is three holes.
    mutationFn: (holeNumbers?: number[]) =>
      api.post<RoundWithGroups>(
        `/tournaments/${id}/rounds`,
        holeNumbers?.length ? { hole_numbers: holeNumbers } : {},
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tournament', id] }),
  });
}

export function useCompleteRound(tournamentId: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (roundId: UUID) => api.post<Round>(`/rounds/${roundId}/complete`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tournament', tournamentId] }),
  });
}

export function useCreateCourse() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; location?: string }) =>
      api.post<Course>('/courses', body),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.courses }),
  });
}

export function useUpsertHoles(courseId: UUID) {
  const client = useQueryClient();
  return useMutation({
    // A full replacement, not a delta: the endpoint takes the whole set of holes
    // being played, so the editor always submits every one of them.
    mutationFn: (holes: { hole_number: number; par?: number | null }[]) =>
      api.put(`/courses/${courseId}/holes`, { holes }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.course(courseId) }),
  });
}

export function useSubmitHole(groupId: UUID, tournamentId: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      holeId: UUID;
      strokes: Record<UUID, number>;
      closest_to_pin?: UUID;
      longest_drive?: UUID;
    }) =>
      api.post<HoleResult>(`/groups/${groupId}/holes/${body.holeId}/scores`, {
        strokes: body.strokes,
        ...(body.closest_to_pin ? { closest_to_pin: body.closest_to_pin } : {}),
        ...(body.longest_drive ? { longest_drive: body.longest_drive } : {}),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.card(groupId) });
      // The scorer's own board should move without waiting for the round trip
      // through Supabase — they are the one person who already knows.
      void client.invalidateQueries({ queryKey: ['tournament', tournamentId] });
    },
  });
}
