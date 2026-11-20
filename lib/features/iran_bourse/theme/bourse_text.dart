import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';

/// Text colours for the Iranian Bourse screens that follow the active app theme (light or dark).
///
/// `AppTokens.body / bodySecondary / caption ...` have fixed dark-theme colours (near-white text),
/// which are invisible on the light themes. Everything here takes its colour from
/// `Theme.of(context).colorScheme.onSurface`, like the rest of the app. Green / red / amber
/// signal colours stay in `AppTokens`.
abstract class BourseText {
  static Color primaryColor(BuildContext context) => Theme.of(context).colorScheme.onSurface;

  static Color secondaryColor(BuildContext context) =>
      Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.65);

  static Color mutedColor(BuildContext context) =>
      Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5);

  static Color accentColor(BuildContext context) => Theme.of(context).colorScheme.primary;

  static Color cardColor(BuildContext context) => Theme.of(context).colorScheme.surface;

  static Color borderColor(BuildContext context) => Theme.of(context).dividerColor;

  /// Shared card and input radii matching the main alert wizard.
  static const double cardRadius = 14.0;
  static const double inputRadius = 12.0;

  /// Amber for warnings: the normal amber is too pale on the light themes, so those get a darker one.
  static Color warningColor(BuildContext context) => Theme.of(context).brightness == Brightness.light
      ? const Color(0xFFB45309)
      : AppTokens.warning;

  static TextStyle appBarTitle(BuildContext context) =>
      TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: primaryColor(context));

  static TextStyle sectionLabel(BuildContext context) =>
      TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: primaryColor(context));

  static TextStyle body(BuildContext context) =>
      TextStyle(fontSize: 13, height: 1.4, color: primaryColor(context));

  static TextStyle secondary(BuildContext context) =>
      TextStyle(fontSize: 13, color: secondaryColor(context));

  static TextStyle caption(BuildContext context) =>
      TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: secondaryColor(context));

  static TextStyle header(BuildContext context) =>
      TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: primaryColor(context));

  /// Compact monospace price number used inside list cards.
  static TextStyle rowPrice(BuildContext context) => TextStyle(
      fontFamily: 'monospace', fontSize: 13, fontWeight: FontWeight.bold, color: primaryColor(context));

  /// Big price number on the detail card.
  static TextStyle price(BuildContext context) => TextStyle(
      fontFamily: 'monospace', fontSize: 24, fontWeight: FontWeight.w600, color: primaryColor(context));

  /// Unified filled rounded input decoration matching the rest of the wizard.
  static InputDecoration inputDecoration(
    BuildContext context, {
    String? labelText,
    String? hintText,
    Widget? prefixIcon,
  }) {
    final theme = Theme.of(context);
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(inputRadius),
      borderSide: BorderSide(color: theme.dividerColor),
    );
    return InputDecoration(
      labelText: labelText,
      hintText: hintText,
      prefixIcon: prefixIcon,
      filled: true,
      fillColor: theme.colorScheme.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: border,
      enabledBorder: border,
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(inputRadius),
        borderSide: BorderSide(color: theme.colorScheme.primary, width: 1.5),
      ),
    );
  }
}
