import 'package:flutter/services.dart';

/// Helper to send the Android activity into the background (mimicking pressing the Home button),
/// allowing the app's Dart background timers, WebSocket connections, and periodic polling services
/// to continue running without getting killed by the OS when the user presses Back.
class AppLifecycleHelper {
  static const MethodChannel _channel =
      MethodChannel('com.example.bitcoin_checker/app_lifecycle');

  static Future<void> moveToBackground() async {
    try {
      final success = await _channel.invokeMethod<bool>('sendToBackground');
      if (success != true) {
        await SystemNavigator.pop();
      }
    } catch (_) {
      try {
        await SystemNavigator.pop();
      } catch (_) {}
    }
  }

  /// Opens the OEM-specific Autostart permission screen directly (Xiaomi, Samsung, Huawei, Oppo, Vivo, etc.)
  static Future<bool> openAutostartSettings() async {
    try {
      final result = await _channel.invokeMethod<bool>('openAutostartSettings');
      return result == true;
    } catch (_) {
      return false;
    }
  }

  /// Opens the app's system details settings page directly
  static Future<bool> openAppSettings() async {
    try {
      final result = await _channel.invokeMethod<bool>('openAppSettings');
      return result == true;
    } catch (_) {
      return false;
    }
  }

  /// Opens system battery optimization settings
  static Future<bool> openBatteryOptimizationSettings() async {
    try {
      final result = await _channel.invokeMethod<bool>('openBatteryOptimizationSettings');
      return result == true;
    } catch (_) {
      return false;
    }
  }
}
