import 'package:flutter/material.dart';

class AppTheme {
  // Paleta
  static const _primary = Color(0xFF0B4F6C);
  static const _accent = Color(0xFFFF6B6B);
  static const _bg = Color(0xFFF3F5F7);
  static const _text = Color(0xFF1E2A32);

  static ThemeData light() {
    final scheme = ColorScheme.fromSeed(
      seedColor: _primary,
      brightness: Brightness.light,
      primary: _primary,
      secondary: _primary,
      surface: Colors.white,
      background: _bg,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: _bg,
      appBarTheme: const AppBarTheme(
        backgroundColor: const Color(0xFFD8DEE6),
        foregroundColor: _text,
        elevation: 0,
      ),
      textTheme: const TextTheme(
        titleMedium: TextStyle(color: _text, fontWeight: FontWeight.w600),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 12,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(22),
          borderSide: const BorderSide(color: Color(0xFFCED4DA)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(22),
          borderSide: const BorderSide(color: Color(0xFFCED4DA)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(22),
          borderSide: BorderSide(color: _primary, width: 2),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: _accent,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(22),
          ),
        ),
      ),
      cardTheme: CardThemeData(
        color: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: Colors.white.withOpacity(.14),
        selectedColor: _primary.withOpacity(.22),
        labelStyle: const TextStyle(
          color: Colors.black,
          fontWeight: FontWeight.w600,
        ),
        shape: StadiumBorder(
          side: BorderSide(color: Colors.white.withOpacity(.35)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
      dividerColor: const Color(0xFFE9EEF3),
    );
  }
}
