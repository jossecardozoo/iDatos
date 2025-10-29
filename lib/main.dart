import 'package:flutter/material.dart';
import 'home_landing.dart';
import 'theme.dart';

void main() => runApp(const MonteroomApp());

class MonteroomApp extends StatelessWidget {
  const MonteroomApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MONTEROOM',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: const HomeLanding(),
    );
  }
}
