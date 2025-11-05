import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../../listing.dart';

class MapView extends StatelessWidget {
  final List<Listing> listings;
  const MapView({super.key, required this.listings});

  @override
  Widget build(BuildContext context) {
    // Filtrar solo las propiedades con lat/lon válidas
    final valid = listings
        .where((l) => l.lat.isFinite && l.lon.isFinite)
        .toList();

    // Centro por defecto: Montevideo
    final LatLng center = valid.isNotEmpty
        ? LatLng(valid.first.lat, valid.first.lon)
        : const LatLng(-34.9011, -56.1645);

    // Marcadores
    final markers = valid.map((l) {
      return Marker(
        width: 32,
        height: 32,
        point: LatLng(l.lat, l.lon),
        child: Icon(
          Icons.location_on,
          size: 28,
          color: Theme.of(context).colorScheme.primary,
        ),
      );
    }).toList();

    return FlutterMap(
      options: MapOptions(initialCenter: center, initialZoom: 12),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.monteroom.app',
        ),
        MarkerLayer(markers: markers),
      ],
    );
  }
}
