/// Result of attempting to show a critical alert banner.
///
/// - [shown]: the banner was actually displayed by the OS. The alert must be
///   committed (deactivated / triggered / cooldown) exactly as before.
/// - [duplicate]: another isolate already showed this alert within the dedup
///   window. The alert is already committed by that isolate; commit locally
///   as well so the UI reflects the final state.
/// - [failed]: the banner could not be shown (plugin threw, or notifications
///   are disabled at the OS level). The alert must NOT be committed so the
///   scheduler retries on the next interval.
enum AlertDispatchResult { shown, duplicate, failed }