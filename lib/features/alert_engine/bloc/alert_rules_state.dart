import 'package:equatable/equatable.dart';
import '../models/alert_rule.dart';

enum AlertRulesStatus { initial, loading, loaded, error }

class AlertRulesState extends Equatable {
  final AlertRulesStatus status;
  final List<AlertRule> rules;
  final String? errorMessage;
  final String? lastTriggeredMessage;

  const AlertRulesState({
    this.status = AlertRulesStatus.initial,
    this.rules = const [],
    this.errorMessage,
    this.lastTriggeredMessage,
  });

  /// Active rules currently being monitored
  List<AlertRule> get activeRules => rules.where((r) => r.isActive).toList();

  /// Rules currently in the 3-minute cooldown period
  List<AlertRule> get coolingDownRules => rules.where((r) => r.isInCooldown).toList();

  AlertRulesState copyWith({
    AlertRulesStatus? status,
    List<AlertRule>? rules,
    String? errorMessage,
    String? lastTriggeredMessage,
  }) {
    return AlertRulesState(
      status: status ?? this.status,
      rules: rules ?? this.rules,
      errorMessage: errorMessage ?? this.errorMessage,
      lastTriggeredMessage: lastTriggeredMessage ?? this.lastTriggeredMessage,
    );
  }

  @override
  List<Object?> get props => [status, rules, errorMessage, lastTriggeredMessage];
}
