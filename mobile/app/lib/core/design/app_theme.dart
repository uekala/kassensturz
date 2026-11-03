import 'package:flutter/material.dart';

/// The visual foundation of Kassensturz.
///
/// The palette is deliberately restrained: warm neutral surfaces, a deep
/// evergreen primary and a small number of semantic accents. Components should
/// rely on these tokens instead of introducing one-off decorative colours.
abstract final class AppTheme {
  static const Color brand = Color(0xFF174A3E);
  static const Color accent = Color(0xFF287A65);
  static const Color canvas = Color(0xFFF5F7F5);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color ink = Color(0xFF18231F);
  static const Color mutedInk = Color(0xFF66736D);
  static const Color border = Color(0xFFE3E9E5);
  static const Color softBrand = Color(0xFFE7F0EC);

  static ThemeData light() {
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: brand,
          brightness: Brightness.light,
          surface: surface,
        ).copyWith(
          primary: brand,
          onPrimary: Colors.white,
          primaryContainer: softBrand,
          onPrimaryContainer: brand,
          secondary: accent,
          onSecondary: Colors.white,
          secondaryContainer: const Color(0xFFEAF2EE),
          onSecondaryContainer: brand,
          surface: surface,
          onSurface: ink,
          surfaceContainerLowest: Colors.white,
          surfaceContainerLow: const Color(0xFFFAFBFA),
          surfaceContainer: canvas,
          surfaceContainerHigh: const Color(0xFFEEF2EF),
          onSurfaceVariant: mutedInk,
          outline: const Color(0xFFB8C4BD),
          outlineVariant: border,
          error: const Color(0xFFB54745),
          onError: Colors.white,
          errorContainer: const Color(0xFFFCEBE9),
          onErrorContainer: const Color(0xFF7A2826),
        );

    const radius = 14.0;

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: canvas,
      splashFactory: InkSparkle.splashFactory,
      appBarTheme: const AppBarTheme(
        backgroundColor: canvas,
        foregroundColor: ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        centerTitle: false,
        titleSpacing: 20,
        toolbarHeight: 62,
        titleTextStyle: TextStyle(
          color: ink,
          fontSize: 20,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.35,
        ),
      ),
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
          color: ink,
          fontSize: 30,
          height: 1.15,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.9,
        ),
        headlineMedium: TextStyle(
          color: ink,
          fontSize: 26,
          height: 1.2,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.65,
        ),
        headlineSmall: TextStyle(
          color: ink,
          fontSize: 23,
          height: 1.25,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.55,
        ),
        titleLarge: TextStyle(
          color: ink,
          fontSize: 18,
          height: 1.3,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.25,
        ),
        titleMedium: TextStyle(
          color: ink,
          fontSize: 15,
          height: 1.35,
          fontWeight: FontWeight.w600,
        ),
        bodyLarge: TextStyle(
          color: ink,
          fontSize: 15,
          height: 1.45,
          fontWeight: FontWeight.w400,
        ),
        bodyMedium: TextStyle(
          color: mutedInk,
          fontSize: 14,
          height: 1.45,
          fontWeight: FontWeight.w400,
        ),
        bodySmall: TextStyle(
          color: mutedInk,
          fontSize: 12,
          height: 1.4,
          fontWeight: FontWeight.w400,
        ),
        labelLarge: TextStyle(
          color: ink,
          fontSize: 13,
          height: 1.3,
          fontWeight: FontWeight.w600,
        ),
        labelMedium: TextStyle(
          color: mutedInk,
          fontSize: 12,
          height: 1.3,
          fontWeight: FontWeight.w600,
        ),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
          side: const BorderSide(color: border),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: border,
        thickness: 1,
        space: 1,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: surface,
        elevation: 0,
        indicatorColor: softBrand,
        height: 72,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        iconTheme: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return IconThemeData(color: selected ? brand : mutedInk, size: 22);
        }),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            color: selected ? brand : mutedInk,
            fontSize: 11,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
          );
        }),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: brand,
          foregroundColor: Colors.white,
          minimumSize: const Size(48, 48),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: brand,
          minimumSize: const Size(48, 48),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          side: const BorderSide(color: border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 14,
        ),
        hintStyle: const TextStyle(color: mutedInk, fontSize: 14),
        labelStyle: const TextStyle(color: mutedInk, fontSize: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: brand, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFB54745)),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFB54745), width: 1.5),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surface,
        selectedColor: softBrand,
        disabledColor: canvas,
        side: const BorderSide(color: border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        labelStyle: const TextStyle(
          color: ink,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
        secondaryLabelStyle: const TextStyle(
          color: brand,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 7),
      ),
    );
  }
}
