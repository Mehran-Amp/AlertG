/// App-wide feature flags.
///
/// AUTH-OFF-1: Google Sign-In is hidden until the server verifies
/// Google ID tokens (currently the server only trusts the user_id/email
/// in the request body, with no token verification). Until then, users
/// stay as guests and the cloud account feature is hidden.
class AppConfig {
  /// When false, the Google Sign-In button is hidden from Settings and
  /// Watchlist pages, and `GoogleAuthService.promptGoogleSignIn` returns
  /// false without showing any dialog.
  ///
  /// Set to true only after:
  ///   1. The server verifies Google ID tokens (server-side auth).
  ///   2. A real build on a physical device has been tested.
  static const bool kCloudAccountEnabled = false;
}
