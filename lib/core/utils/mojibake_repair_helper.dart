import 'dart:convert';

/// Helper to detect and safely repair Mojibake corrupted Persian/Arabic strings
/// resulting from Latin-1 / Windows-1252 misinterpretations of UTF-8 byte sequences.
class MojibakeRepairHelper {
  static const Map<int, int> _cp1252Map = {
    0x20AC: 0x80, // €
    0x201A: 0x82, // ‚
    0x0192: 0x83, // ƒ
    0x201E: 0x84, // „
    0x2026: 0x85, // …
    0x2020: 0x86, // †
    0x2021: 0x87, // ‡
    0x02C6: 0x88, // ˆ
    0x2030: 0x89, // ‰
    0x0160: 0x8A, // Š
    0x2039: 0x8B, // ‹
    0x0152: 0x8C, // Œ
    0x017D: 0x8E, // Ž
    0x2018: 0x91, // ‘
    0x2019: 0x92, // ’
    0x201C: 0x93, // “
    0x201D: 0x94, // ”
    0x2022: 0x95, // •
    0x2013: 0x96, // –
    0x2014: 0x97, // —
    0x02DC: 0x98, // ˜
    0x2122: 0x99, // ™
    0x0161: 0x9A, // š
    0x203A: 0x9B, // ›
    0x0153: 0x9C, // œ
    0x017E: 0x9E, // ž
    0x0178: 0x9F, // Ÿ
  };

  /// Checks if a string contains at least one authentic Persian or Arabic Unicode character.
  static bool containsPersoArabic(String s) {
    for (int i = 0; i < s.length; i++) {
      final code = s.codeUnitAt(i);
      if ((code >= 0x0600 && code <= 0x06FF) ||
          (code >= 0xFB50 && code <= 0xFEFF) ||
          code == 0x200C) {
        return true;
      }
    }
    return false;
  }

  /// Counts the presence of Mojibake sentinel characters in a string.
  static int _countMojibakeChars(String s) {
    int count = 0;
    for (int i = 0; i < s.length; i++) {
      final ch = s[i];
      if (ch == 'Ã' || ch == 'Ø' || ch == 'Ù' || ch == 'Â') {
        count++;
      }
    }
    return count;
  }

  /// Repairs corrupted strings (patterns containing Ã, Ø, Ù, Â) by converting Latin-1 / CP1252 to UTF-8
  /// up to 3 passes.
  ///
  /// CRITICAL ANTI-FALSE-POSITIVE GUARD:
  /// Substitution is ONLY accepted if:
  /// 1. The result produces valid Persian/Arabic characters (`containsPersoArabic == true`).
  /// 2. Valid European text (e.g. "Ørsted", "São Paulo") is NEVER altered because it yields no Persian chars.
  static String? repair(String? input) {
    if (input == null || input.isEmpty) return input;

    String current = input;

    for (int pass = 0; pass < 3; pass++) {
      final initialMojibakeCount = _countMojibakeChars(current);
      if (initialMojibakeCount == 0) {
        break;
      }

      final List<int> bytes = [];
      bool canConvert = true;

      for (int i = 0; i < current.length; i++) {
        final code = current.codeUnitAt(i);
        if (code <= 0xFF) {
          bytes.add(code);
        } else if (_cp1252Map.containsKey(code)) {
          bytes.add(_cp1252Map[code]!);
        } else {
          canConvert = false;
          break;
        }
      }

      if (!canConvert || bytes.isEmpty) {
        break;
      }

      try {
        final decoded = utf8.decode(bytes);

        // Anti-False-Positive verification:
        // Only accept if it actually recovered Persian/Arabic text and reduced/eliminated mojibake artifacts.
        if (containsPersoArabic(decoded) && _countMojibakeChars(decoded) < initialMojibakeCount) {
          current = decoded;
        } else {
          // If decoding didn't produce Persian/Arabic characters, abort pass to preserve legitimate European text
          break;
        }
      } catch (_) {
        break;
      }
    }

    return current;
  }
}

/// Standalone convenience function
String? repairMojibake(String? input) => MojibakeRepairHelper.repair(input);
