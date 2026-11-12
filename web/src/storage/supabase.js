// Part 9: browser port of database/. Planned; nothing here is implemented yet.
// Must give the same results as the Python reference (checked by the parity tests, see web/README.md).

/**
 * Supabase client with the public anon key only (never the service-role key); Row Level Security does the rest
 */
export function connect(url, anonKey) {
  throw new Error("Part 9: connect is not implemented yet");
}

/**
 * Reviewer sign-in (expert or community role)
 */
export function signIn(client, email) {
  throw new Error("Part 9: signIn is not implemented yet");
}

/**
 * Store particle rows (and crops or photos, once Drive 9b is decided)
 */
export function saveRun(client, image, rows) {
  throw new Error("Part 9: saveRun is not implemented yet");
}

/**
 * Store confirmed and corrected labels for retraining
 */
export function saveReview(client, decisions) {
  throw new Error("Part 9: saveReview is not implemented yet");
}
