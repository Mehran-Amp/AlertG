/// One choice in a filter drop-down (market or instrument type).
class BourseFilterOption {
  /// Value sent to the server (`market=` / `type=`), always a String.
  final String code;

  /// Persian label shown to the user.
  final String label;

  /// How many instruments carry this code (0 when unknown). Used only for ordering.
  final int count;

  const BourseFilterOption({required this.code, required this.label, this.count = 0});
}

/// Filter choices built from `GET /api/iran-bourse/classification`.
class BourseFilterOptions {
  final List<BourseFilterOption> markets;
  final List<BourseFilterOption> types;

  const BourseFilterOptions({required this.markets, required this.types});

  static const BourseFilterOptions empty = BourseFilterOptions(markets: [], types: []);

  /// Builds the options from the classification object (`{codes:{...}, observed:{...}}`).
  /// Tolerant: anything unexpected is skipped. Never throws.
  static BourseFilterOptions fromClassification(Map<String, dynamic>? classification) {
    if (classification == null) return empty;
    final codes = classification['codes'];
    final observed = classification['observed'];
    return BourseFilterOptions(
      markets: _build(
        codes is Map ? codes['markets'] : null,
        observed is Map ? observed['markets'] : null,
      ),
      types: _build(
        codes is Map ? codes['types'] : null,
        observed is Map ? observed['types'] : null,
      ),
    );
  }

  static List<BourseFilterOption> _build(Object? codeTable, Object? observedRows) {
    // code -> Persian name from the documented code table
    final names = <String, String>{};
    if (codeTable is Map) {
      codeTable.forEach((key, value) {
        if (value is Map) {
          final name = value['name_fa'];
          if (name is String && name.trim().isNotEmpty) names['$key'] = name.trim();
        }
      });
    }

    final byCode = <String, BourseFilterOption>{};
    if (observedRows is List) {
      for (final row in observedRows) {
        if (row is! Map) continue;
        final code = row['code'];
        if (code is! String || code.isEmpty) continue;
        final rawLabel = row['label'];
        final label = (rawLabel is String && rawLabel.trim().isNotEmpty)
            ? rawLabel.trim()
            : (names[code] ?? code);
        final count = row['count'] is num ? (row['count'] as num).toInt() : 0;
        byCode[code] = BourseFilterOption(code: code, label: label, count: count);
      }
    }
    names.forEach((code, label) {
      byCode.putIfAbsent(code, () => BourseFilterOption(code: code, label: label));
    });

    final list = byCode.values.toList()
      ..sort((a, b) {
        final byCount = b.count.compareTo(a.count);
        return byCount != 0 ? byCount : a.code.compareTo(b.code);
      });

    // Several codes can share one Persian name (for example three kinds of "سهام"):
    // add the code in brackets so the user can tell them apart.
    final labelUses = <String, int>{};
    for (final o in list) {
      labelUses[o.label] = (labelUses[o.label] ?? 0) + 1;
    }
    return [
      for (final o in list)
        (labelUses[o.label] ?? 0) > 1
            ? BourseFilterOption(code: o.code, label: '${o.label} (${o.code})', count: o.count)
            : o,
    ];
  }
}
