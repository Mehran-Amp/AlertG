import 'package:equatable/equatable.dart';
import '../models/alert_rule.dart';

abstract class AlertRulesEvent extends Equatable {
  const AlertRulesEvent();

  @override
  List<Object?> get props => [];
}

/// Dispatched to start listening to the local Isar database stream
class LoadAlertRules extends AlertRulesEvent {
  const LoadAlertRules();
}

/// Dispatched when the database emits an updated list of rules
class AlertRulesUpdated extends AlertRulesEvent {
  final List<AlertRule> rules;

  const AlertRulesUpdated(this.rules);

  @override
  List<Object?> get props => [rules];
}

/// Dispatched to create and save a new alert rule
class CreateAlertRule extends AlertRulesEvent {
  final AlertRule rule;

  const CreateAlertRule(this.rule);

  @override
  List<Object?> get props => [rule];
}

/// Dispatched to update an existing alert rule
class UpdateAlertRule extends AlertRulesEvent {
  final AlertRule rule;

  const UpdateAlertRule(this.rule);

  @override
  List<Object?> get props => [rule];
}

/// Dispatched to toggle an alert rule's active/paused state
class ToggleAlertRule extends AlertRulesEvent {
  final String uuid;
  final bool isActive;

  const ToggleAlertRule({
    required this.uuid,
    required this.isActive,
  });

  @override
  List<Object?> get props => [uuid, isActive];
}

/// Dispatched to delete an alert rule
class DeleteAlertRule extends AlertRulesEvent {
  final String uuid;

  const DeleteAlertRule(this.uuid);

  @override
  List<Object?> get props => [uuid];
}

/// Dispatched to manually re-arm a triggered one-shot rule (or reset cooldown)
class RearmAlertRule extends AlertRulesEvent {
  final String uuid;

  const RearmAlertRule(this.uuid);

  @override
  List<Object?> get props => [uuid];
}
