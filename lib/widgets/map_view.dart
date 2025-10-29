import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../../listing.dart';

class MapView extends StatelessWidget {
  final List<Listing> listings;
  const MapView({super.key, required this.listings});

  @override
  Widget build(BuildContext context) {
    final center = LatLng(-34.9011, -56.1645); // Montevideo

    return FlutterMap(
      options: MapOptions(initialCenter: center, initialZoom: 12),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.monteroom.app',
        ),
        MarkerLayer(
          markers: listings.map((l) {
            final lat = l.coords[0];
            final lon = l.coords[1];
            return Marker(
              width: 40,
              height: 40,
              point: LatLng(lat, lon),
              child: Icon(
                Icons.location_on,
                size: 30,
                color: Theme.of(context).colorScheme.primary,
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}
