import '../models/alert_dispatch_result.dart';

/// Abstract interface for the notification dispatcher.
///
/// The real [NotificationService] is a singleton with a private constructor,
/// which makes it impossible to subclass in tests. This interface lets us
/// inject a fake implementation in tests without touching the singleton.
abstract class NotificationServiceInterface {
  Future<AlertDispatchResult> enqueueCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String? soundName,
    double volume,
    bool soundEnabled,
    bool vibrationEnabled,
    bool ttsEnabled,
    String? speechText,
    bool inAppFeedback,
    bool waitForSpeech,
    Duration maxWait,
  });
}