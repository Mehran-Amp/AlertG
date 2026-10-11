import 'package:flutter/material.dart';

/// Semantic Design Tokens for Alarmer.
/// Colors and text styles adapt to the active Material 3 theme.
abstract class AppTokens {
  // Brand Accents
  static const Color positive = Color(0xFF10B981); // Green up
  static const Color negative = Color(0xFFF43F5E); // Rose down
  static const Color warning = Color(0xFFF59E0B);  // Amber (Cooldown/Caution)
  static const Color warningSubtle = Color(0x26F59E0B);

  // Spacing Scale
  static const double space2 = 2.0;
  static const double space4 = 4.0;
  static const double space6 = 6.0;
  static const double space8 = 8.0;
  static const double space12 = 12.0;
  static const double space14 = 14.0;
  static const double space16 = 16.0;
  static const double space20 = 20.0;
  static const double space24 = 24.0;
  static const double space32 = 32.0;

  // Border Radii
  static const double radiusSmall = 8.0;
  static const double radiusMedium = 12.0;
  static const double radiusLarge = 16.0;
  static const double radiusFull = 9999.0;

  static const BorderRadius borderSmall = BorderRadius.all(Radius.circular(radiusSmall));
  static const BorderRadius borderMedium = BorderRadius.all(Radius.circular(radiusMedium));
  static const BorderRadius borderLarge = BorderRadius.all(Radius.circular(radiusLarge));
  static const BorderRadius borderFull = BorderRadius.all(Radius.circular(radiusFull));

  // Legacy static fallbacks (prefer Theme.of(context))
  static const Color background = Color(0xFF090D16);
  static const Color surface = Color(0xFF111827);
  static const Color surfaceElevated = Color(0xFF1F2937);
  static const Color border = Color(0xFF374151);
  static const Color borderSubtle = Color(0xFF1F2937);
  static const Color primary = Color(0xFF10B981);
  static const Color secondary = Color(0xFF06B6D4);
  static const Color primarySubtle = Color(0x2610B981);
  static const Color textPrimary = Color(0xFFF9FAFB);
  static const Color textSecondary = Color(0xFF9CA3AF);
  static const Color textMuted = Color(0xFF6B7280);

  // Typography Tokens
  static const TextStyle caption = TextStyle(
    fontSize: 11.0,
    fontWeight: FontWeight.w500,
    color: textSecondary,
  );

  static const TextStyle body = TextStyle(
    fontSize: 13.0,
    fontWeight: FontWeight.normal,
    color: textPrimary,
    height: 1.4,
  );

  static const TextStyle bodySecondary = TextStyle(
    fontSize: 13.0,
    fontWeight: FontWeight.normal,
    color: textSecondary,
  );

  static const TextStyle sectionHeader = TextStyle(
    fontSize: 15.0,
    fontWeight: FontWeight.w600,
    color: textPrimary,
  );

  static const TextStyle monoNumbers = TextStyle(
    fontFamily: 'monospace',
    fontSize: 14.0,
    fontWeight: FontWeight.w600,
    color: textPrimary,
  );

  // Helper dynamic getters
  static TextStyle titleStyle(BuildContext context) {
    final theme = Theme.of(context);
    return TextStyle(
      fontSize: 18.0,
      fontWeight: FontWeight.w700,
      color: theme.colorScheme.onSurface,
      letterSpacing: -0.3,
    );
  }

  static TextStyle headerStyle(BuildContext context) {
    final theme = Theme.of(context);
    return TextStyle(
      fontSize: 15.0,
      fontWeight: FontWeight.w600,
      color: theme.colorScheme.onSurface,
    );
  }

  static TextStyle bodyStyle(BuildContext context) {
    final theme = Theme.of(context);
    return TextStyle(
      fontSize: 13.0,
      fontWeight: FontWeight.w400,
      color: theme.colorScheme.onSurface,
      height: 1.4,
    );
  }

  static TextStyle subStyle(BuildContext context) {
    final theme = Theme.of(context);
    return TextStyle(
      fontSize: 12.0,
      fontWeight: FontWeight.w400,
      color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
    );
  }
}
