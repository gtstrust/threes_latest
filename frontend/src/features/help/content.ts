/**
 * Every word of the explainer, kept out of the components that render it.
 *
 * Two reasons for the split, and the second is the one that matters. React Fast
 * Refresh only reloads a module cleanly when it exports components alone, which
 * is why `format.ts` and `session-context.ts` sit apart from theirs. And content
 * with no JSX in it can be checked by a plain test — that every topic points at a
 * step that exists is the kind of thing that rots silently otherwise.
 *
 * **The voice is the app's, not a help voice.** Most of what follows is lifted
 * from a screen that already says it: the tie-break questions come from
 * `ScorePage`, the ranking rules from `LeaderboardPage`, the two formats from
 * `NewTournamentPage`. A player who reads this and then meets the screen should
 * hear the same person twice. A brighter, more explanatory register would read as
 * something bolted on afterwards, which is exactly what it is.
 */

/**
 * Who a step is for. Players meet the format; organisers also have to run it.
 *
 * A union rather than an enum: `erasableSyntaxOnly` (tsconfig.app.json) rejects
 * any type-directed syntax that emits runtime code, and `enum` emits an object.
 */
export type Track = 'player' | 'organiser';

export type Step = {
  /** Slug, and what `?step=` carries. Stable — help panels link to these. */
  id: string;
  track: Track;
  title: string;
  /** Paragraphs. Short ones; this is read standing up. */
  body: string[];
};

export type Topic = {
  title: string;
  body: string[];
  /** Where "How Threes works" lands from this panel. */
  step: string;
};

/**
 * The walkthrough, in order. Player steps first, then the organiser ones.
 *
 * Six for a player, which is the number that fits the format without padding:
 * what a loop is, who you play, how a hole is won, what happens when it isn't,
 * how the board reads, and that there is more than one round.
 */
export const STEPS: Step[] = [
  {
    id: 'format',
    track: 'player',
    title: 'Three holes, not eighteen',
    body: [
      'A loop is three holes. That is the whole competition — you play your three, and you are done.',
      'It means a field can start together and finish together, which is why the format suits a day where everybody has somewhere to be afterwards.',
    ],
  },
  {
    id: 'group',
    track: 'player',
    title: 'Your group is your match',
    body: [
      'You are drawn into a group of two to four. Threes is the format and the usual size. That group is your match: you play the three holes against the people in it, and nobody else on the course affects them.',
      'Your group, who you are with and your starting hole are all on the event screen.',
      'A shotgun start can wrap the turn, so your loop might read 17, 18, 1. That is the order to play them in, not a mistake.',
    ],
  },
  {
    id: 'points',
    track: 'player',
    title: 'One hole, one winner',
    body: [
      'Fewest strokes on a hole takes it, and that is worth one point. Everyone else in the group scores zero.',
      'Holes are never halved. A hole has exactly one winner or no winner at all, so there are no half-points and every score is a whole number.',
      'Only strokes decide it. Par is not used, so a par-3 and a par-5 are worth the same point.',
    ],
  },
  {
    id: 'ties',
    track: 'player',
    title: 'If you tie, we ask',
    body: [
      'Tie on strokes and the app asks the group a question: who was closest to the pin? Only these players tied, so only they can win the hole.',
      'Still level, and it asks a second: who hit the longest drive on the fairway? A drive that finished in the rough does not count, however long.',
      'If nobody reached the green and nobody found the fairway, nobody wins the hole and everyone scores zero for it.',
      'Nothing is recorded unless it actually decided a hole, which is why you are only asked when it matters.',
    ],
  },
  {
    id: 'board',
    track: 'player',
    title: 'Reading the board',
    body: [
      'Points first. Level players are split by fewest total strokes.',
      'In a knockout the board is ranked by how far a player got, then points, then fewest total strokes — so the champion is top even if somebody knocked out earlier won more holes along the way.',
      'The board moves on its own as groups score. Nobody has to refresh it.',
    ],
  },
  {
    id: 'rounds',
    track: 'player',
    title: 'More than one round',
    body: [
      'An event usually runs several rounds, and the groups are drawn again for each one, so you do not play the same people twice.',
      'Round robin — everyone plays every round, and the leaderboard adds up.',
      'Knockout — each group winner goes through. Everyone else is done, and the board records how far they got.',
    ],
  },

  {
    id: 'handicaps',
    track: 'player',
    title: 'Handicaps, if your event uses them',
    body: [
      'Most events are scratch: lowest gross wins the hole, and that is the whole rule. Some are not.',
      'On a handicap event your playing handicap is pro-rated to the three holes you are playing, and those shots are dealt to the hardest of them first — the stroke index a club prints on its card.',
      'Your net score on a hole is what you took, less any shot you got there. Everything else is unchanged: the hole still has exactly one winner, the tie-break questions are still the same two, and the board still splits level players on fewest strokes — net ones.',
      'You will see both numbers everywhere. Gross is what your group counted; net is what decided it.',
    ],
  },
  {
    id: 'setup',
    track: 'organiser',
    title: 'Setting up an event',
    body: [
      'An event needs a name to exist. The course, the tee time and the maximum players can all be filled in later, right up until you draw.',
      'A maximum stops the field growing past what you booked. It only applies to players joining themselves — you can always add someone yourself.',
      'The format is the exception: round robin or knockout is fixed when the event is created, because the whole shape of the day follows from it.',
    ],
  },
  {
    id: 'draw',
    track: 'organiser',
    title: 'Drawing the round',
    body: [
      'Open registration, then share the join link or let people scan the QR. They sign in and they are in the field.',
      'Somebody without a phone can be added by you, and their group enters their scores for them.',
      'Drawing the round is what starts play. It makes the groups, gives each one its holes, and fixes the field — so draw when everybody who is coming has arrived.',
    ],
  },
  {
    id: 'formats',
    track: 'organiser',
    title: 'Threes or fourballs, blocks or shotgun',
    body: [
      'Threes is the format and the default. Fourballs exist for arithmetic rather than taste: a shotgun start needs one tee per group and a course has eighteen, so sixty-four players in threes will not fit, and in fourballs it will.',
      'Blocks cuts the course into 3-hole loops, so eighteen holes make six.',
      'A shotgun makes every hole a starting tee, so eighteen holes make eighteen loops and far more groups tee off at once. Past whichever ceiling applies, groups share a loop and tee off staggered.',
    ],
  },
  {
    id: 'finishing',
    track: 'organiser',
    title: 'Finishing a round, and the day',
    body: [
      'Finish the round once the field is in. That closes its scores, and in a knockout it records who goes through from each group.',
      'A knockout group can finish completely level — nothing separated them on points, on strokes, or on who won a hole later. The app will not guess; it asks you to pick who goes through before the next round can be drawn.',
      'When one player is left they have won the day, and finishing the tournament is yours to press.',
    ],
  },
];

/**
 * What each screen's help panel says.
 *
 * Keyed by the string a screen passes to `HelpPanel`. Deliberately two or three
 * sentences: this answers the question the player has *right now*, and anything
 * longer belongs in the walkthrough that `step` points at.
 */
export const TOPICS: Record<string, Topic> = {
  scoring: {
    title: 'Entering scores',
    body: [
      'Tap plus or minus for each player, then save. Everyone in the group needs a number before the hole can be scored.',
      'If two of you tie on strokes, the app asks who was closest to the pin, and then who hit the longest drive on the fairway.',
      'Got one wrong? Pick the hole again and save it with the right number.',
    ],
    step: 'ties',
  },
  card: {
    title: 'The card',
    body: [
      'Every hole your group has played, with each player’s strokes. A ring marks the hole that player took.',
      'Underneath is how each hole was decided — fewest strokes, closest to the pin, longest drive, or nobody could be separated.',
    ],
    step: 'points',
  },
  board: {
    title: 'How the board is ranked',
    body: [
      'Points first, then fewest total strokes.',
      'In a knockout, Reached is how far a player got, and it leads the ranking — so the champion is top even if somebody else won more holes.',
      'It updates itself as groups score.',
    ],
    step: 'board',
  },
  'your-group': {
    title: 'Your group',
    body: [
      'Your group is your match. You play your three holes against the people in it, and nobody else on the course affects them.',
      'Start on the hole shown. A shotgun loop can wrap the turn, so 17, 18, 1 is the order to play, not a mistake.',
    ],
    step: 'group',
  },
  'run-the-day': {
    title: 'Running the day',
    body: [
      'Open registration, share the link or QR, then draw the round. Drawing is what starts play, and it fixes the field.',
      'Finish the round when everybody is in, then draw the next one — or finish the tournament.',
    ],
    step: 'draw',
  },
  invitation: {
    title: 'What is Threes?',
    body: [
      'Golf over three holes instead of eighteen. You are drawn into a small group, that group is your match, and each hole has exactly one winner.',
      'Joining puts you in the field. You can look around first.',
    ],
    step: 'format',
  },
  formats: {
    title: 'Round robin or knockout',
    body: [
      'Round robin — everyone plays every round, and the leaderboard adds up.',
      'Knockout — each group winner goes through. Everyone else is done.',
      'This one is fixed once the event exists, so it is worth getting right now.',
    ],
    step: 'rounds',
  },
  'draw-settings': {
    title: 'Group size and start style',
    body: [
      'Threes is the format. Fourballs fit a bigger field into a shotgun start, because a shotgun needs a tee per group and a course has eighteen.',
      'Blocks cuts the course into 3-hole loops. A shotgun makes every hole a starting tee, so more groups go off at once.',
    ],
    step: 'formats',
  },
  handicaps: {
    title: 'Handicaps on this event',
    body: [
      'Shots come off a gross score, dealt to the hardest holes of the loop by stroke index.',
      'Every player needs a handicap and every hole being played needs a stroke index. The draw says so, by name, if either is missing.',
    ],
    step: 'handicaps',
  },
  'fun-round': {
    title: 'Fun rounds',
    body: [
      'A fun round is one group of up to four — no organiser, no rounds, just your three holes and a board.',
      'Scoring is identical to a tournament: one winner a hole, and the same two tie-break questions.',
    ],
    step: 'points',
  },
};

/** The steps of one track, in order. */
export function stepsFor(track: Track): Step[] {
  return STEPS.filter((step) => step.track === track);
}

/**
 * Resolve `?step=` to a step, its position, and the track it belongs to.
 *
 * An unknown or absent slug answers with the first player step rather than an
 * error. A stale link in somebody's messages should open the explainer at the
 * beginning, not show them a broken page — there is nothing here worth failing
 * over.
 *
 * The track is derived from the step rather than carried separately, so
 * `?step=draw` puts the reader in the organiser track with nothing else to keep
 * in step.
 */
export function findStep(id: string | null): { step: Step; index: number; of: Step[] } {
  const found = STEPS.find((step) => step.id === id) ?? STEPS[0];
  const of = stepsFor(found.track);
  return { step: found, index: of.indexOf(found), of };
}
