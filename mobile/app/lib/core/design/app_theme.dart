import 'package:flutter/material.dart';

/// The colours of one brightness. Widgets read them with
/// `KlarColors.of(context)` so the same layout works light and dark.
@immutable
class KlarColors extends ThemeExtension<KlarColors> {
  const KlarColors({
    required this.brand,
    required this.onBrand,
    required this.surface,
    required this.ink,
    required this.mutedInk,
    required this.border,
    required this.fieldBorder,
    required this.softBrand,
    required this.warn,
    required this.softWarn,
    required this.onSoftWarn,
  });

  /// The one accent: actions, progress, income.
  final Color brand;
  final Color onBrand;

  /// Page and panel background; there are no tinted or grey panels.
  final Color surface;
  final Color ink;
  final Color mutedInk;

  /// Hairlines between rows.
  final Color border;

  /// Outlines of inputs and filter buttons.
  final Color fieldBorder;

  /// Tint behind brand-coloured content, and the track of progress bars.
  final Color softBrand;

  /// What needs attention: over budget, errors, lost connection.
  final Color warn;
  final Color softWarn;
  final Color onSoftWarn;

  static const light = KlarColors(
    brand: Color(0xFF1F4FE0),
    onBrand: Color(0xFFFFFFFF),
    surface: Color(0xFFFFFFFF),
    ink: Color(0xFF101418),
    mutedInk: Color(0xFF4A5560),
    border: Color(0xFFD5DBE3),
    fieldBorder: Color(0xFF9AA3AE),
    softBrand: Color(0xFFE4EAFD),
    warn: Color(0xFFB4470A),
    softWarn: Color(0xFFFBEADF),
    onSoftWarn: Color(0xFF6E2A05),
  );

  static const dark = KlarColors(
    brand: Color(0xFF8FB0FF),
    onBrand: Color(0xFF0B1220),
    surface: Color(0xFF0F1216),
    ink: Color(0xFFF2F4F7),
    mutedInk: Color(0xFFA9B2BD),
    border: Color(0xFF2A313A),
    fieldBorder: Color(0xFF5F6A76),
    softBrand: Color(0xFF1A274D),
    warn: Color(0xFFFF9E63),
    softWarn: Color(0xFF3A2212),
    onSoftWarn: Color(0xFFFFD2B5),
  );

  static KlarColors of(BuildContext context) =>
      Theme.of(context).extension<KlarColors>() ?? light;

  @override
  KlarColors copyWith({
    Color? brand,
    Color? onBrand,
    Color? surface,
    Color? ink,
    Color? mutedInk,
    Color? border,
    Color? fieldBorder,
    Color? softBrand,
    Color? warn,
    Color? softWarn,
    Color? onSoftWarn,
  }) {
    return KlarColors(
      brand: brand ?? this.brand,
      onBrand: onBrand ?? this.onBrand,
      surface: surface ?? this.surface,
      ink: ink ?? this.ink,
      mutedInk: mutedInk ?? this.mutedInk,
      border: border ?? this.border,
      fieldBorder: fieldBorder ?? this.fieldBorder,
      softBrand: softBrand ?? this.softBrand,
      warn: warn ?? this.warn,
      softWarn: softWarn ?? this.softWarn,
      onSoftWarn: onSoftWarn ?? this.onSoftWarn,
    );
  }

  @override
  KlarColors lerp(ThemeExtension<KlarColors>? other, double t) {
    if (other is! KlarColors) return this;
    return KlarColors(
      brand: Color.lerp(brand, other.brand, t)!,
      onBrand: Color.lerp(onBrand, other.onBrand, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      ink: Color.lerp(ink, other.ink, t)!,
      mutedInk: Color.lerp(mutedInk, other.mutedInk, t)!,
      border: Color.lerp(border, other.border, t)!,
      fieldBorder: Color.lerp(fieldBorder, other.fieldBorder, t)!,
      softBrand: Color.lerp(softBrand, other.softBrand, t)!,
      warn: Color.lerp(warn, other.warn, t)!,
      softWarn: Color.lerp(softWarn, other.softWarn, t)!,
      onSoftWarn: Color.lerp(onSoftWarn, other.onSoftWarn, t)!,
    );
  }
}

/// The visual foundation of Kassensturz.
///
/// One surface colour, strong ink and one blue. Shapes are drawn with ink
/// outlines instead of tinted fills; orange marks what needs attention.
/// Text is set in Inter, headings and large amounts in Space Grotesk.
abstract final class AppTheme {
  static const textFamily = 'Inter';
  static const displayFamily = 'Space Grotesk';

  /// Glyphs beyond Western European (for example Turkish or Polish names).
  static const textFallback = ['Inter Ext'];
  static const displayFallback = ['Space Grotesk Ext', 'Inter', 'Inter Ext'];

  static ThemeData light() => _build(Brightness.light, KlarColors.light);

  static ThemeData dark() => _build(Brightness.dark, KlarColors.dark);

  static ThemeData _build(Brightness brightness, KlarColors c) {
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: KlarColors.light.brand,
          brightness: brightness,
          surface: c.surface,
        ).copyWith(
          primary: c.brand,
          onPrimary: c.onBrand,
          primaryContainer: c.softBrand,
          onPrimaryContainer: c.brand,
          secondary: c.brand,
          onSecondary: c.onBrand,
          secondaryContainer: c.softBrand,
          onSecondaryContainer: c.brand,
          surface: c.surface,
          onSurface: c.ink,
          surfaceContainerLowest: c.surface,
          surfaceContainerLow: c.surface,
          surfaceContainer: c.surface,
          surfaceContainerHigh: c.softBrand,
          surfaceContainerHighest: c.softBrand,
          onSurfaceVariant: c.mutedInk,
          outline: c.fieldBorder,
          outlineVariant: c.border,
          error: c.warn,
          onError: c.onBrand,
          errorContainer: c.softWarn,
          onErrorContainer: c.onSoftWarn,
        );

    const radius = 16.0;

    TextStyle display(double size, double spacing, {double height = 1.15}) {
      return TextStyle(
        fontFamily: displayFamily,
        fontFamilyFallback: displayFallback,
        color: c.ink,
        fontSize: size,
        height: height,
        fontWeight: FontWeight.w700,
        letterSpacing: spacing,
      );
    }

    TextStyle text(Color color, double size, FontWeight weight, double height) {
      return TextStyle(
        color: color,
        fontSize: size,
        height: height,
        fontWeight: weight,
      );
    }

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      extensions: [c],
      fontFamily: textFamily,
      fontFamilyFallback: textFallback,
      scaffoldBackgroundColor: c.surface,
      splashFactory: InkSparkle.splashFactory,
      appBarTheme: AppBarTheme(
        backgroundColor: c.surface,
        foregroundColor: c.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        centerTitle: false,
        titleSpacing: 20,
        toolbarHeight: 62,
        titleTextStyle: display(22, -0.5),
      ),
      textTheme: TextTheme(
        headlineLarge: display(30, -0.9),
        headlineMedium: display(26, -0.65, height: 1.2),
        headlineSmall: display(28, -0.8),
        titleLarge: text(c.ink, 18, FontWeight.w700, 1.3),
        titleMedium: text(c.ink, 15, FontWeight.w600, 1.35),
        bodyLarge: text(c.ink, 15, FontWeight.w400, 1.45),
        bodyMedium: text(c.mutedInk, 14, FontWeight.w400, 1.45),
        bodySmall: text(c.mutedInk, 12, FontWeight.w400, 1.4),
        labelLarge: text(c.ink, 13, FontWeight.w600, 1.3),
        labelMedium: text(c.mutedInk, 12, FontWeight.w600, 1.3),
      ),
      cardTheme: CardThemeData(
        color: c.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
          side: BorderSide(color: c.ink, width: 1.5),
        ),
      ),
      dividerTheme: DividerThemeData(color: c.border, thickness: 1, space: 1),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: c.ink,
        contentTextStyle: TextStyle(color: c.surface, fontSize: 14),
        behavior: SnackBarBehavior.floating,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: c.brand,
          foregroundColor: c.onBrand,
          minimumSize: const Size(48, 48),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: c.ink,
          minimumSize: const Size(48, 48),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          side: BorderSide(color: c.ink, width: 1.5),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: c.brand),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: c.surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 14,
        ),
        hintStyle: TextStyle(color: c.mutedInk, fontSize: 14),
        labelStyle: TextStyle(color: c.mutedInk, fontSize: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c.fieldBorder, width: 1.5),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c.fieldBorder, width: 1.5),
        ),
        disabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c.border, width: 1.5),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c.brand, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c.warn, width: 1.5),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: c.warn, width: 2),
        ),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          backgroundColor: WidgetStateProperty.resolveWith(
            (states) =>
                states.contains(WidgetState.selected) ? c.ink : c.surface,
          ),
          foregroundColor: WidgetStateProperty.resolveWith(
            (states) =>
                states.contains(WidgetState.selected) ? c.surface : c.ink,
          ),
          side: WidgetStatePropertyAll(BorderSide(color: c.ink, width: 1.5)),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: c.ink, width: 1.5),
        ),
      ),
    );
  }
}
