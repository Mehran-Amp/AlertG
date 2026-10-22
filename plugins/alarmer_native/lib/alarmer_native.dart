import 'package:flutter/services.dart';

/// Thin Dart wrapper around the native alarmer_native plugin.
///
/// The plugin registers `com.example.bitcoin_checker/app_lifecycle` on every
/// FlutterEngine, so this wrapper works from the main UI isolate, the FCM
/// background isolate, and the foreground-service isolate alike.
class AlarmerNative {
  static const MethodChannel _channel =
      MethodChannel('com.example.bitcoin_checker/app_lifecycle');

  static Future<void> speak({
    required String text,
    String lang = 'en',
    double rate = 1.0,
    double pitch = 1.0,
  }) async {
    await _channel.invokeMethod('speak', {
      'text': text,
      'lang': lang,
      'rate': rate,
      'pitch': pitch,
    });
  }

  static Future<void> stopSpeak() async {
    await _channel.invokeMethod('stopSpeak');
  }

  static Future<void> playAlarm({
    String sound = 'alarm_siren',
    bool vibrate = true,
    double volume = 1.0,
  }) async {
    await _channel.invokeMethod('playAlarm', {
      'sound': sound,
      'vibrate': vibrate,
      'volume': volume,
    });
  }

  static Future<void> stopAlarm() async {
    await _channel.invokeMethod('stopAlarm');
  }
}