import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:bitcoin_checker/core/services/google_auth_service.dart';
import 'package:bitcoin_checker/features/settings/services/settings_service.dart';

class FakeGoogleSignInAccount implements GoogleSignInAccount {
  @override
  final String email;
  @override
  final String? displayName;
  @override
  final String? photoUrl;
  @override
  final String id;
  @override
  final String? serverAuthCode;

  FakeGoogleSignInAccount({
    required this.email,
    this.displayName,
    this.photoUrl,
    this.id = 'fake-google-id-123',
    this.serverAuthCode,
  });

  @override
  Future<GoogleSignInAuthentication> get authentication =>
      throw UnimplementedError();

  @override
  Future<Map<String, String>> get authHeaders => Future.value({});

  @override
  Future<void> clearAuthCache() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late SettingsService settingsService;

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('auth_test_');
    settingsService = SettingsService(tempDir.path);
    GoogleAuthService.signInOverride = null;
    GoogleAuthService.signOutOverride = null;
    GoogleAuthService.forceAccountChooserInvoked = false;
  });

  tearDown(() {
    GoogleAuthService.signInOverride = null;
    GoogleAuthService.signOutOverride = null;
    GoogleAuthService.forceAccountChooserInvoked = false;
    try {
      tempDir.deleteSync(recursive: true);
    } catch (_) {}
  });

  group('GoogleAuthService Phase 1: Force Account Chooser & Complete Logout', () {
    test('1. Google sign-in forces account chooser by purging previous session before signIn', () async {
      bool signOutCalledBeforeSignIn = false;
      bool signInCalled = false;

      GoogleAuthService.signOutOverride = () async {
        signOutCalledBeforeSignIn = true;
      };

      GoogleAuthService.signInOverride = () async {
        // Verify that signOut was already executed prior to signIn (forcing account chooser prompt)
        expect(signOutCalledBeforeSignIn, isTrue);
        signInCalled = true;
        return FakeGoogleSignInAccount(
          email: 'trader@example.com',
          displayName: 'Pro Trader',
        );
      };

      final account = await GoogleAuthService.signIn();

      expect(GoogleAuthService.forceAccountChooserInvoked, isTrue);
      expect(signOutCalledBeforeSignIn, isTrue);
      expect(signInCalled, isTrue);
      expect(account?.email, equals('trader@example.com'));
      expect(account?.displayName, equals('Pro Trader'));
    });

    test('2. Complete logout invokes GoogleAuthService.signOut and SettingsService.signOut', () async {
      bool googleSignOutCalled = false;

      GoogleAuthService.signOutOverride = () async {
        googleSignOutCalled = true;
      };

      // Simulate an active user session in SettingsService
      await settingsService.signInWithGoogle(
        email: 'trader@example.com',
        displayName: 'Pro Trader',
        photoUrl: 'https://example.com/avatar.png',
      );
      expect(settingsService.settings.isSignedInWithGoogle, isTrue);
      expect(settingsService.settings.userEmail, equals('trader@example.com'));

      // Perform complete logout
      await GoogleAuthService.signOut();
      await settingsService.signOut();

      // Assert both signouts executed
      expect(googleSignOutCalled, isTrue, reason: 'GoogleAuthService.signOut must be called to purge Google session');
      expect(settingsService.settings.isSignedInWithGoogle, isFalse, reason: 'SettingsService.signOut must clear user state');
      expect(settingsService.settings.userEmail, isNull);
    });

    test('3. Google sign-in handles user cancellation without modifying settings', () async {
      GoogleAuthService.signOutOverride = () async {};
      GoogleAuthService.signInOverride = () async => null; // User cancelled

      final account = await GoogleAuthService.signIn();

      expect(account, isNull);
      expect(settingsService.settings.isSignedInWithGoogle, isFalse);
      expect(settingsService.settings.userEmail, isNull);
    });
  });
}
