import 'package:flutter/material.dart';
import '../../listing.dart';

class ListingCard extends StatelessWidget {
  final Listing listing;
  const ListingCard({super.key, required this.listing});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      clipBehavior: Clip.antiAlias,
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _HouseThumbnail(
              imageUrl: listing.imagenUrl,
              semanticLabel:
                  'Imagen del inmueble: ${listing.tipo} en ${listing.barrio ?? 'Barrio no disponible'}',
            ),
            const SizedBox(width: 12),

            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Título
                  Text(
                    listing.titulo,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 6),

                  // Pills básicas
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
                        '${listing.dorms?.toStringAsFixed(0) ?? '-'} dorm',
                        bg: const Color(0xFFF1F5F9),
                        fg: const Color(0xFF334155),
                      ),
                      _pill(
                        listing.tipo,
                        bg: const Color(0xFFEFF6FF),
                        fg: const Color(0xFF1D4ED8),
                      ),
                    ],
                  ),

                  // NUEVO: Distancias y seguridad (si vienen)
                  const SizedBox(height: 8),
                  _contextChips(listing),

                  const SizedBox(height: 8),

                  // Precio
                  Text(
                    '\$${listing.precioUYU?.toStringAsFixed(0) ?? '-'} UYU',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),

                  const SizedBox(height: 8),

                  // Acciones
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      TextButton(
                        onPressed: () {
                          // TODO: usar listing.lat / listing.lon
                        },
                        child: const Text('Ver en mapa'),
                      ),
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
          ],
        ),
      ),
    );
  }
}

class _HouseThumbnail extends StatelessWidget {
  final String? imageUrl;
  final String? semanticLabel;
  const _HouseThumbnail({this.imageUrl, this.semanticLabel});

  @override
  Widget build(BuildContext context) {
    final surfaceVariant = Theme.of(context).colorScheme.surfaceVariant;
    final onSurface = Theme.of(context).colorScheme.onSurface;

    Widget placeholder = Container(
      color: surfaceVariant.withOpacity(0.5),
      child: const AspectRatio(aspectRatio: 1, child: _CenteredHouseIcon()),
    );

    Widget content;
    if (imageUrl == null || imageUrl!.isEmpty) {
      content = placeholder;
    } else {
      content = AspectRatio(
        aspectRatio: 1,
        child: Image.network(
          imageUrl!,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => Center(
            child: Icon(
              Icons.broken_image_outlined,
              size: 28,
              color: onSurface.withOpacity(0.65),
            ),
          ),
          loadingBuilder: (ctx, child, progress) {
            if (progress == null) return child;
            return placeholder;
          },
        ),
      );
    }

    return Semantics(
      label: semanticLabel,
      image: true,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: 88,
          constraints: const BoxConstraints(minHeight: 88),
          child: content,
        ),
      ),
    );
  }
}

class _CenteredHouseIcon extends StatelessWidget {
  const _CenteredHouseIcon();
  @override
  Widget build(BuildContext context) {
    final onSurface = Theme.of(context).colorScheme.onSurface;
    return Center(
      child: Icon(
        Icons.home_filled,
        size: 36,
        color: onSurface.withOpacity(0.75),
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

Widget _contextChips(Listing l) {
  final chips = <Widget>[];

  String _fmtDist(double m) => m >= 1000
      ? '${(m / 1000).toStringAsFixed(1)} km'
      : '${m.toStringAsFixed(0)} m';

  Color _crimeFg(String n) {
    switch (n.toLowerCase()) {
      case 'alta':
        return const Color(0xFFDC2626); // rojo
      case 'media':
        return const Color(0xFFF59E0B); // ámbar
      case 'baja':
        return Colors.green.shade700; // verde
      default:
        return const Color(0xFF334155); // gris
    }
  }

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

  if (l.distanciaParada != null) {
    chips.add(
      chip(Icons.directions_bus, 'Parada a ${_fmtDist(l.distanciaParada!)}'),
    );
  }
  if (l.distanciaBicicircuito != null) {
    chips.add(
      chip(Icons.pedal_bike, 'Bici a ${_fmtDist(l.distanciaBicicircuito!)}'),
    );
  }
  if (l.nivelCriminalidad != null && l.nivelCriminalidad!.isNotEmpty) {
    final c = _crimeFg(l.nivelCriminalidad!);
    chips.add(
      chip(
        Icons.security,
        'Seguridad ${l.nivelCriminalidad}',
        fg: c,
        bg: c.withOpacity(.12),
      ),
    );
  }

  if (chips.isEmpty) return const SizedBox.shrink();
  return Wrap(spacing: 8, runSpacing: 6, children: chips);
}
