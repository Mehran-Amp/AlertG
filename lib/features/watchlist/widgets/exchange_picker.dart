import 'package:flutter/material.dart';
import '../../../core/theme/tokens.dart';
import '../../exchanges/registry/exchange_registry.dart';

/// Exchange selector widget that lets the user choose the price source
/// from exchanges that offer the selected trading pair.
class ExchangePicker extends StatelessWidget {
  final List<String> availableExchangeIds;
  final String? selectedExchangeId;
  final ExchangeRegistry registry;
  final ValueChanged<String> onExchangeSelected;

  const ExchangePicker({
    super.key,
    required this.availableExchangeIds,
    required this.selectedExchangeId,
    required this.registry,
    required this.onExchangeSelected,
  });

  @override
  Widget build(BuildContext context) {
    if (availableExchangeIds.isEmpty) {
      return const SizedBox.shrink();
    }

    final sortedExchangeIds = List<String>.from(availableExchangeIds)..sort((a, b) {
      final nameA = registry.get(a)?.name ?? a;
      final nameB = registry.get(b)?.name ?? b;
      return nameA.toLowerCase().compareTo(nameB.toLowerCase());
    });

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Select Price Source Exchange',
          style: AppTokens.caption.copyWith(color: AppTokens.textSecondary),
        ),
        const SizedBox(height: AppTokens.space8),
        Wrap(
          spacing: AppTokens.space8,
          runSpacing: AppTokens.space8,
          children: sortedExchangeIds.map((exId) {
            final exchange = registry.get(exId);
            final name = exchange?.name ?? exId.toUpperCase();
            final isSelected = selectedExchangeId == exId;

            return ChoiceChip(
              label: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.account_balance_rounded,
                    size: 14,
                    color: isSelected ? AppTokens.primary : AppTokens.textSecondary,
                  ),
                  const SizedBox(width: AppTokens.space6),
                  Text(name),
                ],
              ),
              selected: isSelected,
              onSelected: (_) => onExchangeSelected(exId),
              selectedColor: AppTokens.primarySubtle,
              backgroundColor: AppTokens.surface,
              side: BorderSide(
                color: isSelected ? AppTokens.primary : AppTokens.borderSubtle,
              ),
              labelStyle: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: isSelected ? AppTokens.primary : AppTokens.textPrimary,
              ),
              shape: const RoundedRectangleBorder(borderRadius: AppTokens.borderMedium),
            );
          }).toList(),
        ),
      ],
    );
  }
}
