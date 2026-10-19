import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../../../core/services/server_alert_service.dart';
import '../../notifications/services/notification_service.dart';
import '../models/market_event.dart';

/// Service responsible for managing, persisting, and triggering
/// 30-minute advance reminders for high-impact Market Events.
class EventReminderService {
  static final EventReminderService instance = EventReminderService._internal();
  EventReminderService._internal();

  final ValueNotifier<Set<String>> activeRemindersNotifier = ValueNotifier<Set<String>>({});
  final Map<String, Timer> _activeTimers = {};
  bool _initialized = false;

  Set<String> get activeReminderIds => activeRemindersNotifier.value;

  Future<File> _getFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/event_reminders.json');
  }

  /// Initialize and load saved reminder states from local storage
  Future<void> init() async {
    if (_initialized) return;
    try {
      final file = await _getFile();
      if (await file.exists()) {
        final content = await file.readAsString();
        if (content.trim().isNotEmpty) {
          final decoded = jsonDecode(content);
          if (decoded is List) {
            final ids = decoded.map((e) => e.toString()).toSet();
            activeRemindersNotifier.value = ids;
          }
        }
      }
    } catch (e) {
      debugPrint('⚠️ [EventReminderService] Init error: $e');
    }
    _initialized = true;
  }

  bool isReminderSet(String eventId) {
    return activeRemindersNotifier.value.contains(eventId);
  }

  /// Toggles reminder state for a market event.
  /// Returns `true` if reminder is now active, `false` if cancelled.
  Future<bool> toggleReminder(BuildContext context, MarketEvent event) async {
    await init();
    final isCurrentlySet = isReminderSet(event.id);

    if (isCurrentlySet) {
      await _cancelReminder(context, event);
      return false;
    } else {
      await _scheduleReminder(context, event);
      return true;
    }
  }

  Future<void> _scheduleReminder(BuildContext context, MarketEvent event) async {
    final newSet = Set<String>.from(activeRemindersNotifier.value)..add(event.id);
    activeRemindersNotifier.value = newSet;
    await _saveToDisk();

    // Calculate event target time and 30-minute advance trigger
    final eventTime = parseEventDateTime(event.timeUtc);
    final nowUtc = DateTime.now().toUtc();
    final reminderTime = eventTime.subtract(const Duration(minutes: 30));

    final timeUntilReminder = reminderTime.difference(nowUtc);
    final notificationId = _generateNotificationId(event.id);

    // If reminder time is in the future, schedule timer for current session
    if (timeUntilReminder.inSeconds > 0) {
      _activeTimers[event.id]?.cancel();
      _activeTimers[event.id] = Timer(timeUntilReminder, () {
        _triggerAdvanceNotification(event);
      });
    }

    // Sync with backend so Telegram bot registers the reminder as well
    _syncReminderWithServer(event, cancel: false);

    if (context.mounted) {
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.notifications_active_rounded, color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Reminder set! You will be notified 30 minutes before ${event.symbol} (${event.timeUtc}).',
                  style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          backgroundColor: const Color(0xFF0284C7),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          duration: const Duration(seconds: 4),
        ),
      );
    }
  }

  Future<void> _cancelReminder(BuildContext context, MarketEvent event) async {
    final newSet = Set<String>.from(activeRemindersNotifier.value)..remove(event.id);
    activeRemindersNotifier.value = newSet;
    await _saveToDisk();

    _activeTimers[event.id]?.cancel();
    _activeTimers.remove(event.id);

    final notificationId = _generateNotificationId(event.id);
    await NotificationService().cancelNotification(notificationId);

    // Sync cancellation with backend and Telegram
    _syncReminderWithServer(event, cancel: true);

    if (context.mounted) {
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.notifications_off_rounded, color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Reminder cancelled for ${event.symbol}.',
                  style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          backgroundColor: const Color(0xFF475569),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  Future<void> _saveToDisk() async {
    try {
      final file = await _getFile();
      final list = activeRemindersNotifier.value.toList();
      await file.writeAsString(jsonEncode(list));
    } catch (e) {
      debugPrint('⚠️ [EventReminderService] Save error: $e');
    }
  }

  int _generateNotificationId(String eventId) {
    return (eventId.hashCode.abs() % 100000) + 40000;
  }

  void _triggerAdvanceNotification(MarketEvent event) {
    NotificationService().enqueueCriticalAlert(
      id: _generateNotificationId(event.id),
      title: '⏰ Upcoming Catalyst in 30 Mins: ${event.symbol}',
      body: '${event.title} begins in 30 minutes (${event.timeUtc}). High market volatility expected.',
      soundEnabled: true,
      vibrationEnabled: true,
      ttsEnabled: true,
      speechText: 'Attention. Market catalyst for ${event.symbol} begins in thirty minutes.',
    );
  }

  /// Parses event time strings into the next upcoming UTC DateTime.
  /// Handles "Wednesday 18:00 UTC", "Thursday 12:30 UTC", "Friday 14:00 UTC", etc.
  DateTime parseEventDateTime(String timeUtcStr) {
    final now = DateTime.now().toUtc();
    final clean = timeUtcStr.toUpperCase().replaceAll('UTC', '').trim();

    // Map day names to weekday integers (1 = Monday, 7 = Sunday)
    final daysMap = {
      'MONDAY': DateTime.monday,
      'TUESDAY': DateTime.tuesday,
      'WEDNESDAY': DateTime.wednesday,
      'THURSDAY': DateTime.thursday,
      'FRIDAY': DateTime.friday,
      'SATURDAY': DateTime.saturday,
      'SUNDAY': DateTime.sunday,
    };

    int? targetWeekday;
    for (final entry in daysMap.entries) {
      if (clean.contains(entry.key)) {
        targetWeekday = entry.value;
        break;
      }
    }

    // Extract HH:mm
    final timeMatch = RegExp(r'(\d{1,2}):(\d{2})').firstMatch(clean);
    int hour = 14;
    int minute = 0;
    if (timeMatch != null) {
      hour = int.tryParse(timeMatch.group(1) ?? '14') ?? 14;
      minute = int.tryParse(timeMatch.group(2) ?? '0') ?? 0;
    }

    if (targetWeekday != null) {
      int daysAhead = (targetWeekday - now.weekday) % 7;
      DateTime candidate = DateTime.utc(now.year, now.month, now.day + daysAhead, hour, minute);

      // If already within 30 minutes or passed today, move to next week's occurrence
      if (candidate.isBefore(now.add(const Duration(minutes: 30)))) {
        candidate = candidate.add(const Duration(days: 7));
      }
      return candidate;
    }

    // Default fallback: 4 hours from now
    return now.add(const Duration(hours: 4));
  }

  void _syncReminderWithServer(MarketEvent event, {required bool cancel}) async {
    try {
      final user = await ServerAlertService.getEffectiveUserId();
      await ServerAlertService.post('/api/market-events/remind', body: {
        'user_id': user,
        'event_id': event.id,
        'cancel': cancel,
      });
    } catch (e) {
      debugPrint('ℹ️ [EventReminderService] Server sync note: $e');
    }
  }
}
