import 'package:equatable/equatable.dart';

/// Represents a logged notification event fired when an alert condition triggers.
class NotificationLog extends Equatable {
  final String uuid;
  final String ruleUuid;
  final String exchangeId;
  final String marketSymbol;
  final String title;
  final String message;
  final double triggeredPrice;
  final double? previousPrice;
  final String? customNote;
  final String? conditionType;
  final DateTime timestamp;

  const NotificationLog({
    required this.uuid,
    required this.ruleUuid,
    required this.exchangeId,
    required this.marketSymbol,
    required this.title,
    required this.message,
    required this.triggeredPrice,
    this.previousPrice,
    this.customNote,
    this.conditionType,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
        'uuid': uuid,
        'ruleUuid': ruleUuid,
        'exchangeId': exchangeId,
        'marketSymbol': marketSymbol,
        'title': title,
        'message': message,
        'triggeredPrice': triggeredPrice,
        'previousPrice': previousPrice,
        'customNote': customNote,
        'conditionType': conditionType,
        'timestamp': timestamp.toIso8601String(),
      };

  factory NotificationLog.fromJson(Map<String, dynamic> json) =>
      NotificationLog(
        uuid: json['uuid'] as String,
        ruleUuid: json['ruleUuid'] as String? ?? '',
        exchangeId: json['exchangeId'] as String? ?? '',
        marketSymbol: json['marketSymbol'] as String? ?? '',
        title: json['title'] as String? ?? '',
        message: json['message'] as String? ?? '',
        triggeredPrice: (json['triggeredPrice'] as num?)?.toDouble() ?? 0.0,
        previousPrice: (json['previousPrice'] as num?)?.toDouble() ??
            (json['previous_price'] as num?)?.toDouble(),
        customNote: json['customNote'] as String? ?? json['custom_note'] as String?,
        conditionType: json['conditionType'] as String? ?? json['condition_type'] as String?,
        timestamp: json['timestamp'] != null
            ? DateTime.parse(json['timestamp'] as String)
            : DateTime.now(),
      );

  @override
  List<Object?> get props => [
        uuid,
        ruleUuid,
        exchangeId,
        marketSymbol,
        title,
        message,
        triggeredPrice,
        previousPrice,
        customNote,
        conditionType,
        timestamp,
      ];
}
