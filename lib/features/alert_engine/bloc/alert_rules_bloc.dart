import 'dart:async';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../repositories/json_alert_rule_repository.dart';
import 'alert_rules_event.dart';
import 'alert_rules_state.dart';

/// AlertRulesBloc is a pure CRUD BLoC for user price-alert rules.
/// Talks only to JSON repository via [JsonAlertRuleRepository].
/// Has zero awareness of background evaluation, isolates, or triggers (handled by Scheduler).
class AlertRulesBloc extends Bloc<AlertRulesEvent, AlertRulesState> {
  final JsonAlertRuleRepository _repository;
  StreamSubscription? _rulesSubscription;

  AlertRulesBloc({
    required JsonAlertRuleRepository repository,
  })  : _repository = repository,
        super(const AlertRulesState()) {
    on<LoadAlertRules>(_onLoadAlertRules);
    on<AlertRulesUpdated>(_onAlertRulesUpdated);
    on<CreateAlertRule>(_onCreateAlertRule);
    on<UpdateAlertRule>(_onUpdateAlertRule);
    on<ToggleAlertRule>(_onToggleAlertRule);
    on<DeleteAlertRule>(_onDeleteAlertRule);
    on<RearmAlertRule>(_onRearmAlertRule);
  }

  Future<void> _onLoadAlertRules(
    LoadAlertRules event,
    Emitter<AlertRulesState> emit,
  ) async {
    emit(state.copyWith(status: AlertRulesStatus.loading));
    await _rulesSubscription?.cancel();

    _rulesSubscription = _repository.watchAllRules().listen((rules) {
      add(AlertRulesUpdated(rules));
    });
  }

  void _onAlertRulesUpdated(
    AlertRulesUpdated event,
    Emitter<AlertRulesState> emit,
  ) {
    emit(state.copyWith(
      status: AlertRulesStatus.loaded,
      rules: event.rules,
    ));
  }

  Future<void> _onCreateAlertRule(
    CreateAlertRule event,
    Emitter<AlertRulesState> emit,
  ) async {
    try {
      await _repository.saveRule(event.rule);
    } catch (e) {
      emit(state.copyWith(
        status: AlertRulesStatus.error,
        errorMessage: 'Failed to create rule: $e',
      ));
    }
  }

  Future<void> _onUpdateAlertRule(
    UpdateAlertRule event,
    Emitter<AlertRulesState> emit,
  ) async {
    try {
      await _repository.saveRule(event.rule);
    } catch (e) {
      emit(state.copyWith(
        status: AlertRulesStatus.error,
        errorMessage: 'Failed to update rule: $e',
      ));
    }
  }

  Future<void> _onToggleAlertRule(
    ToggleAlertRule event,
    Emitter<AlertRulesState> emit,
  ) async {
    final existing = state.rules.where((r) => r.uuid == event.uuid).firstOrNull;
    if (existing != null) {
      final updated = existing.copyWith(isActive: event.isActive);
      await _repository.saveRule(updated);
    }
  }

  Future<void> _onDeleteAlertRule(
    DeleteAlertRule event,
    Emitter<AlertRulesState> emit,
  ) async {
    await _repository.deleteRule(event.uuid);
  }

  Future<void> _onRearmAlertRule(
    RearmAlertRule event,
    Emitter<AlertRulesState> emit,
  ) async {
    final existing = state.rules.where((r) => r.uuid == event.uuid).firstOrNull;
    if (existing != null) {
      final rearmed = existing.copyWith(
        isActive: true,
        isTriggered: false,
      );
      await _repository.saveRule(rearmed);
    }
  }

  @override
  Future<void> close() async {
    await _rulesSubscription?.cancel();
    return super.close();
  }
}
