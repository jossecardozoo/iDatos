// lib/widgets/listing_card.dart
import 'package:flutter/material.dart';
import '../../listing.dart';

class ListingCard extends StatelessWidget {
  final Listing listing;
  const ListingCard({super.key, required this.listing});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(listing.titulo, style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),

            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                _pill(
                  listing.barrio ?? 'Barrio N/D',
                  bg: const Color(0xFFE9F6FA),
                  fg: const Color(0xFF0B4F6C),
                ),
                _pill(
                  '${listing.dorms ?? '-'} dorm',
                  bg: const Color(0xFFF1F5F9),
                  fg: const Color(0xFF334155),
                ),
                _pill(
                  '${listing.sup?.toStringAsFixed(0) ?? '-'} m²',
                  bg: const Color(0xFFF1F5F9),
                  fg: const Color(0xFF334155),
                ),
                _pill(
                  listing.tipo,
                  bg: const Color(0xFFEFF6FF),
                  fg: const Color(0xFF1D4ED8),
                ),
                _pill(
                  listing.fuente,
                  bg: const Color(0xFFFFF1F2),
                  fg: const Color(0xFFDC2626),
                ),
              ],
            ),

            if (listing.indicadores != null) ...[
              const SizedBox(height: 8),
              _indicadoresRow(listing, context),
            ],

            const SizedBox(height: 8),

            Text(
              '\$${listing.precioUYU?.toStringAsFixed(0) ?? '-'} UYU  '
              '(\$${listing.precioUSD?.toStringAsFixed(0) ?? '-'} USD)',
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),

            const SizedBox(height: 8),

            Row(
              children: [
                TextButton(
                  onPressed: () {},
                  style: TextButton.styleFrom(
                    foregroundColor: theme.colorScheme.primary,
                  ),
                  child: const Text('Ver en mapa'),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: () {},
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.primary,
                    side: const BorderSide(color: Color(0xFF91A4B7)),
                    shape: const StadiumBorder(),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 18,
                      vertical: 12,
                    ),
                  ),
                  child: const Text('Comparar'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

Chip _pill(String text, {required Color bg, required Color fg}) {
  return Chip(
    label: Text(
      text,
      style: TextStyle(color: fg, fontWeight: FontWeight.w600),
    ),
    backgroundColor: bg,
    shape: StadiumBorder(side: BorderSide(color: fg.withOpacity(.15))),
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
  );
}

Widget _indicadoresRow(Listing l, BuildContext context) {
  final ind = l.indicadores!;
  final chips = <Widget>[];

  Widget chip(IconData icon, String text, {Color? fg, Color? bg}) {
    final cFg = fg ?? const Color(0xFF334155);
    final cBg = bg ?? const Color(0xFFF1F5F9);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: cBg,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: cFg.withOpacity(.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: cFg),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(fontWeight: FontWeight.w600, color: cFg),
          ),
        ],
      ),
    );
  }

  Color segColor(int s) {
    if (s < 40) return const Color(0xFFDC2626); // rojo
    if (s < 70) return const Color(0xFFF59E0B); // ámbar
    return Colors.green.shade700; // verde
  }

  if (ind.paradasCercanas != null) {
    chips.add(chip(Icons.directions_bus, '${ind.paradasCercanas} paradas'));
  }
  if (ind.seguridadScore != null) {
    final c = segColor(ind.seguridadScore!);
    chips.add(
      chip(
        Icons.security,
        'Seguridad ${ind.seguridadScore}',
        fg: c,
        bg: c.withOpacity(.12),
      ),
    );
  }
  if (ind.hospitalesCerca != null) {
    chips.add(chip(Icons.local_hospital, '${ind.hospitalesCerca} hospitales'));
  }
  if (ind.escuelasCerca != null) {
    chips.add(chip(Icons.school, '${ind.escuelasCerca} escuelas'));
  }
  if (ind.supermercadosCerca != null) {
    chips.add(
      chip(Icons.shopping_cart, '${ind.supermercadosCerca} supermercados'),
    );
  }
  if (ind.plazasCerca != null) {
    chips.add(chip(Icons.park, '${ind.plazasCerca} plazas'));
  }

  if (chips.isEmpty) return const SizedBox.shrink();
  return Wrap(spacing: 8, runSpacing: 6, children: chips);
}
