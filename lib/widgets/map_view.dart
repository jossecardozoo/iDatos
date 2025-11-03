import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../../listing.dart';

class MapView extends StatelessWidget {
  final List<Listing> listings;
  const MapView({super.key, required this.listings});

  @override
  Widget build(BuildContext context) {
    final valid = listings.where((l) {
      if (l.coords.length < 2) return false;
      final lat = l.coords[0];
      final lon = l.coords[1];
      return lat.isFinite && lon.isFinite;
    }).toList();

    final LatLng center = valid.isNotEmpty
        ? LatLng(valid.first.coords[0], valid.first.coords[1])
        : const LatLng(-34.9011, -56.1645);

    final markers = valid.map((l) {
      final lat = l.coords[0];
      final lon = l.coords[1];
      return Marker(
        width: 32,
        height: 32,
        point: LatLng(lat, lon),
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
