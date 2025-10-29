import 'package:flutter/material.dart';
import 'listing.dart';
import 'listing_repository.dart';
import 'widgets/listing_card.dart';
import 'widgets/map_view.dart';
import 'home_landing.dart';

class ListingsPage extends StatefulWidget {
  final String? initialQuery;
  final Operacion? initialTipoOperacion;
  final String? initialTipoPropiedad;

  const ListingsPage({
    super.key,
    this.initialQuery,
    this.initialTipoOperacion,
    this.initialTipoPropiedad,
  });

  @override
  State<ListingsPage> createState() => _ListingsPageState();
}

class _ListingsPageState extends State<ListingsPage> {
  final _repo = ListingRepository();
  late Future<List<Listing>> _future;

  @override
  void initState() {
    super.initState();
    _future = _repo.getAll(
      q: widget.initialQuery,
      tipoOperacion: widget.initialTipoOperacion,
      tipoPropiedad: widget.initialTipoPropiedad,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('MONTEROOM'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
      ),
      body: FutureBuilder<List<Listing>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Error: ${snap.error}'));
          }
          final list = snap.data ?? [];
          return Row(
            children: [
              // Lista
              Expanded(
                flex: 2,
                child: ListView.builder(
                  itemCount: list.length,
                  itemBuilder: (_, i) => ListingCard(listing: list[i]),
                ),
              ),
              const VerticalDivider(width: 1),
              // Mapa
              Expanded(flex: 3, child: MapView(listings: list)),
            ],
          );
        },
      ),
    );
  }
}
