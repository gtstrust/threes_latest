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
  CourseSummary,
  CourseWithHoles,
  FunRound,
  FunRoundDetail,
  FunRoundPreview,
  JoinPreview,
  PlayerStats,
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
  funRounds: ['fun-rounds'] as const,
  funRound: (id: UUID) => ['fun-round', id] as const,
  funRoundPreview: (id: UUID) => ['fun-round', id, 'preview'] as const,
  join: (code: string) => ['join', code] as const,
  myStats: ['players', 'me', 'stats'] as const,
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
  return useQuery({
    queryKey: keys.courses,
    queryFn: () => api.get<CourseSummary[]>('/courses'),
  });
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
    mutationFn: (status: string) => api.post<Tournament>(`/tournaments/${id}/status`, { status }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tournament', id] }),
  });
}

export function useAddVirtualPlayer(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (display_name: string) =>
      api.post<Participant>(`/tournaments/${id}/participants/virtual`, {
        display_name,
      }),
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
    mutationFn: (body: { name: string; location?: string }) => api.post<Course>('/courses', body),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.courses }),
  });
}

export function useUpsertHoles() {
  const client = useQueryClient();
  return useMutation({
    // A full replacement, not a delta: the endpoint takes the whole set of holes
    // being played, so the editor always submits every one of them. The course id
    // travels with the call rather than being bound when the hook runs, so a
    // just-created course (whose id the previous render didn't have) is targeted
    // correctly in the same submit.
    mutationFn: ({
      courseId,
      holes,
    }: {
      courseId: UUID;
      holes: { hole_number: number; par?: number | null }[];
    }) => api.put(`/courses/${courseId}/holes`, { holes }),
    onSuccess: (_data, { courseId }) =>
      void client.invalidateQueries({ queryKey: keys.course(courseId) }),
  });
}

// --- Fun Rounds ------------------------------------------------------------

/** Fun rounds you host or have joined. */
export function useFunRounds() {
  return useQuery({
    queryKey: keys.funRounds,
    queryFn: () => api.get<FunRound[]>('/fun-rounds'),
  });
}

export function useFunRound(id: UUID) {
  return useQuery({
    queryKey: keys.funRound(id),
    queryFn: () => api.get<FunRoundDetail>(`/fun-rounds/${id}`),
  });
}

export function useCreateFunRound() {
  const client = useQueryClient();
  return useMutation({
    // The loop is chosen here rather than at start, so it travels with the round
    // from the moment it exists and the server can check it against the course
    // while the host is still on the form.
    mutationFn: (body: { name: string; course_id?: UUID; hole_numbers?: number[] }) =>
      api.post<FunRoundDetail>('/fun-rounds', body),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.funRounds }),
  });
}

/**
 * What an invitee sees before joining. The one fun-round read open to anyone
 * signed in, which is what makes the shared link work as an invite.
 */
export function useFunRoundPreview(id: UUID, enabled = true) {
  return useQuery({
    queryKey: keys.funRoundPreview(id),
    queryFn: () => api.get<FunRoundPreview>(`/fun-rounds/${id}/preview`),
    enabled,
  });
}

export function useJoinFunRound(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Participant>(`/fun-rounds/${id}/players`, {}),
    onSuccess: () => {
      // funRound(id) is the prefix of funRoundPreview(id), so the invitation
      // screen's own data is refetched by the same call that unlocks the full
      // round — the join is the moment both answers change.
      void client.invalidateQueries({ queryKey: keys.funRound(id) });
      void client.invalidateQueries({ queryKey: keys.funRounds });
    },
  });
}

export function useAddVirtualToFunRound(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (display_name: string) =>
      api.post<Participant>(`/fun-rounds/${id}/virtual`, { display_name }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.funRound(id) }),
  });
}

export function useStartFunRound(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    // A fun round is one loop, so a hole selection is exactly three. Omitted means
    // play whatever was chosen at setup — which is the normal case, since that is
    // where the host picks.
    mutationFn: (holeNumbers?: number[]) =>
      api.post<FunRoundDetail>(
        `/fun-rounds/${id}/start`,
        holeNumbers?.length ? { hole_numbers: holeNumbers } : {},
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.funRound(id) }),
  });
}

export function useFinishFunRound(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<FunRoundDetail>(`/fun-rounds/${id}/finish`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.funRound(id) });
      void client.invalidateQueries({ queryKey: keys.funRounds });
    },
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

// --- Invitations -----------------------------------------------------------

/** What a join code names. Open to anyone signed in — the code is the credential. */
export function useJoinPreview(code: string) {
  return useQuery({
    queryKey: keys.join(code),
    queryFn: () => api.get<JoinPreview>(`/join/${code}`),
    // An invitation is read once and acted on; a stale one would offer a button
    // for a round that filled up while the page sat open.
    staleTime: 0,
  });
}

export function useAcceptInvitation(code: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Participant>(`/join/${code}`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.join(code) });
      void client.invalidateQueries({ queryKey: keys.playing });
      void client.invalidateQueries({ queryKey: keys.funRounds });
    },
  });
}

/** Retire the current invitation and mint a new one. Organiser only. */
export function useRegenerateJoinCode(id: UUID) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ join_code: string }>(`/tournaments/${id}/join-code`),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.tournament(id) }),
  });
}

/** The caller's own record. No id in the path — their token is the filter. */
export function useMyStats() {
  return useQuery({
    queryKey: keys.myStats,
    queryFn: () => api.get<PlayerStats>('/players/me/stats'),
  });
}
