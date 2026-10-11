import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/crypto_icons.dart';
import '../../exchanges/base/currency_pair.dart';
import '../../exchanges/registry/exchange_registry.dart';
import '../../settings/services/settings_service.dart';

class SearchResultItem {
  final CurrencyPair pair;
  final List<String> availableExchangeIds;

  const SearchResultItem({
    required this.pair,
    required this.availableExchangeIds,
  });
}

/// Search field with debounced query across exchanges.
/// Displays matching pairs with real crypto logos & popular quick-pick chips.
class AssetSearchField extends StatefulWidget {
  final ExchangeRegistry exchangeRegistry;
  final ValueChanged<SearchResultItem> onPairSelected;

  const AssetSearchField({
    super.key,
    required this.exchangeRegistry,
    required this.onPairSelected,
  });

  @override
  State<AssetSearchField> createState() => _AssetSearchFieldState();
}

class _AssetSearchFieldState extends State<AssetSearchField> {
  final TextEditingController _controller = TextEditingController();
  Timer? _debounceTimer;
  List<SearchResultItem> _results = [];
  bool _isSearching = false;

  final List<String> _popularCoins = [
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'PEPE', 'SHIB', 'TON', 'SUI', 'ADA', 'AVAX', 'NEAR'
  ];

  @override
  void dispose() {
    _debounceTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    _debounceTimer?.cancel();
    final clean = query.trim();
    if (clean.isEmpty) {
      setState(() {
        _results = [];
        _isSearching = false;
      });
      return;
    }

    setState(() => _isSearching = true);
    _debounceTimer = Timer(const Duration(milliseconds: 250), () async {
      final searchMap = await widget.exchangeRegistry.searchPairsAcrossExchanges(clean);
      final Map<String, SearchResultItem> aggregated = {};

      for (final entry in searchMap.entries) {
        final exchangeId = entry.key;
        for (final pair in entry.value) {
          final key = '${pair.baseCurrency}/${pair.counterCurrency}';
          if (!aggregated.containsKey(key)) {
            aggregated[key] = SearchResultItem(
              pair: pair,
              availableExchangeIds: [exchangeId],
            );
          } else {
            aggregated[key]!.availableExchangeIds.add(exchangeId);
          }
        }
      }

      if (mounted) {
        setState(() {
          _results = aggregated.values.toList();
          _isSearching = false;
        });
      }
    });
  }

  void _selectPopular(String base) {
    _controller.text = base;
    _onSearchChanged(base);
  }

  @override
  Widget build(BuildContext context) {
    final lang = context.watch<SettingsService>().settings.language;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _controller,
          onChanged: _onSearchChanged,
          autofocus: true,
          style: AppTokens.body,
          decoration: InputDecoration(
            hintText: AppStrings.get('search_crypto_hint', lang),
            hintStyle: AppTokens.bodySecondary,
            prefixIcon: const Icon(Icons.search_rounded, color: AppTokens.primary),
            suffixIcon: _isSearching
                ? const Padding(
                    padding: EdgeInsets.all(AppTokens.space12),
                    child: SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: AppTokens.primary),
                    ),
                  )
                : (_controller.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear_rounded, color: AppTokens.textMuted),
                        onPressed: () {
                          _controller.clear();
                          _onSearchChanged('');
                        },
                      )
                    : null),
            filled: true,
            fillColor: AppTokens.surface,
            border: const OutlineInputBorder(borderRadius: AppTokens.borderMedium),
          ),
        ),

        const SizedBox(height: AppTokens.space12),

        // Popular Coin Chips
        Text(
          AppStrings.get('popular_cryptos', lang),
          style: AppTokens.caption.copyWith(color: AppTokens.textSecondary, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: AppTokens.space8),
        Wrap(
          spacing: AppTokens.space6,
          runSpacing: AppTokens.space6,
          children: _popularCoins.map((coin) {
            return InkWell(
              onTap: () => _selectPopular(coin),
              borderRadius: AppTokens.borderSmall,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppTokens.surface,
                  borderRadius: AppTokens.borderSmall,
                  border: Border.all(color: AppTokens.borderSubtle),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CryptoIcons.buildLogo(coin, size: 16),
                    const SizedBox(width: AppTokens.space6),
                    Text(
                      coin,
                      style: AppTokens.caption.copyWith(
                        color: AppTokens.textPrimary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),

        if (_results.isNotEmpty) ...[
          const SizedBox(height: AppTokens.space12),
          Container(
            constraints: const BoxConstraints(maxHeight: 260),
            decoration: BoxDecoration(
              color: AppTokens.surface,
              borderRadius: AppTokens.borderMedium,
              border: Border.all(color: AppTokens.borderSubtle),
            ),
            child: ListView.separated(
              shrinkWrap: true,
              itemCount: _results.length,
              separatorBuilder: (_, __) => const Divider(height: 1, color: AppTokens.borderSubtle),
              itemBuilder: (context, index) {
                final item = _results[index];
                return ListTile(
                  leading: CryptoIcons.buildLogo(item.pair.baseCurrency, size: 32),
                  title: Text(
                    item.pair.displayName,
                    style: AppTokens.sectionHeader.copyWith(fontSize: 15),
                  ),
                  subtitle: Row(
                    children: [
                      Text('${AppStrings.get('exchange', lang)}: ', style: AppTokens.caption),
                      ...item.availableExchangeIds.map((ex) => Container(
                            margin: const EdgeInsets.only(right: AppTokens.space4),
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                            decoration: const BoxDecoration(
                              color: AppTokens.surfaceElevated,
                              borderRadius: AppTokens.borderSmall,
                            ),
                            child: Text(
                              ex.toUpperCase(),
                              style: AppTokens.caption.copyWith(color: AppTokens.secondary, fontSize: 10, fontWeight: FontWeight.bold),
                            ),
                          )),
                    ],
                  ),
                  trailing: const Icon(Icons.arrow_forward_ios_rounded, size: 14, color: AppTokens.textMuted),
                  onTap: () {
                    widget.onPairSelected(item);
                  },
                );
              },
            ),
          ),
        ],
      ],
    );
  }
}
