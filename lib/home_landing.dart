import 'package:flutter/material.dart';
import 'listings_page.dart';
import '../../listing.dart';
import 'listing_repository.dart';
import 'widgets/listing_card.dart';

enum Operacion { venta, alquiler, temporal, proyectos }

class HomeLanding extends StatefulWidget {
  const HomeLanding({super.key});
  @override
  State<HomeLanding> createState() => _HomeLandingState();
}

class _HomeLandingState extends State<HomeLanding> {
  Operacion op = Operacion.venta;
  final _ubicacionCtrl = TextEditingController();
  String _tipoProp = 'Casa';
  final tipos = const ['Casa', 'Apartamento', 'PH', 'Dúplex', 'Oficina'];

  final _repo = ListingRepository();
  late Future<List<Listing>> _futureHome;

  @override
  void initState() {
    super.initState();
    _futureHome = _loadHomeListings();
  }

  Future<List<Listing>> _loadHomeListings() {
    return _repo.getAll(q: null, tipoOperacion: op, tipoPropiedad: _tipoProp);
  }

  @override
  void dispose() {
    _ubicacionCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'UNIDATOS',
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w800,
          ),
        ),
        actions: const [
          _TopIcon(icon: Icons.person_outline, tooltip: 'Perfil'),
          _TopIcon(icon: Icons.map_outlined, tooltip: 'Mapa'),
          _TopIcon(icon: Icons.help_outline, tooltip: 'Ayuda'),
          SizedBox(width: 8),
        ],
      ),

      body: Column(
        children: [
          Container(
            height: 380,
            width: double.infinity,
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0xFF103C49), Color(0xFF0B4F59)],
              ),
            ),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1080),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _TabsOperacion(
                        value: op,
                        onChanged: (v) {
                          setState(() {
                            op = v;
                            _futureHome =
                                _loadHomeListings(); // refresca listado
                          });
                        },
                      ),
                      const SizedBox(height: 16),

                      Material(
                        elevation: 16,
                        borderRadius: BorderRadius.circular(26),
                        shadowColor: Colors.black.withOpacity(.25),
                        child: Container(
                          decoration: BoxDecoration(
                            color: theme.colorScheme.surface,
                            borderRadius: BorderRadius.circular(26),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(.08),
                                blurRadius: 18,
                                offset: const Offset(0, 8),
                              ),
                            ],
                          ),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 10,
                          ),
                          child: Row(
                            children: [
                              SizedBox(
                                width: 260,
                                child: DropdownButtonFormField<String>(
                                  value: _tipoProp,
                                  decoration: const InputDecoration(
                                    labelText: 'Tipo de propiedad',
                                  ),
                                  items: tipos
                                      .map(
                                        (t) => DropdownMenuItem(
                                          value: t,
                                          child: Text(t),
                                        ),
                                      )
                                      .toList(),
                                  onChanged: (v) {
                                    setState(() {
                                      _tipoProp = v ?? _tipoProp;
                                      _futureHome = _loadHomeListings();
                                    });
                                  },
                                ),
                              ),
                              const SizedBox(width: 10),

                              Expanded(
                                child: TextField(
                                  controller: _ubicacionCtrl,
                                  decoration: const InputDecoration(
                                    hintText:
                                        'Buscá por ubicación o palabra clave',
                                    prefixIcon: Icon(Icons.search),
                                  ),
                                  onSubmitted: (_) => _onBuscar(),
                                ),
                              ),
                              const SizedBox(width: 10),

                              SizedBox(
                                height: 48,
                                child: FilledButton.icon(
                                  onPressed: _onBuscar,
                                  icon: const Icon(Icons.search),
                                  label: const Text('Buscar'),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          Expanded(
            child: Container(
              color: const Color(0xFFF5F7FA),
              child: FutureBuilder<List<Listing>>(
                future: _futureHome,
                builder: (context, snap) {
                  if (snap.connectionState != ConnectionState.done) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (snap.hasError) {
                    return _EmptyState(
                      icon: Icons.error_outline,
                      title: 'Ocurrió un error',
                      subtitle: 'Tocá para reintentar.',
                      action: () => setState(() {
                        _futureHome = _loadHomeListings();
                      }),
                      actionLabel: 'Reintentar',
                    );
                  }
                  final list = snap.data ?? const <Listing>[];
                  if (list.isEmpty) {
                    return _EmptyState(
                      icon: Icons.home_work_outlined,
                      title: 'Sin resultados por ahora',
                      subtitle:
                          'Actualizá para cargar destacados o realizá una búsqueda.',
                      action: () => setState(() {
                        _futureHome = _loadHomeListings();
                      }),
                      actionLabel: 'Actualizar',
                    );
                  }

                  return RefreshIndicator(
                    onRefresh: () async {
                      setState(() {
                        _futureHome = _loadHomeListings();
                      });
                      await _futureHome;
                    },
                    child: ListView.separated(
                      padding: const EdgeInsets.symmetric(
                        vertical: 12,
                        horizontal: 8,
                      ),
                      itemCount: list.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 6),
                      itemBuilder: (context, i) =>
                          ListingCard(listing: list[i]),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _onBuscar() {
    final query = _ubicacionCtrl.text.trim().isEmpty
        ? null
        : _ubicacionCtrl.text.trim();

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ListingsPage(
          initialQuery: query,
          initialTipoOperacion: op,
          initialTipoPropiedad: _tipoProp,
        ),
      ),
    );
  }
}

class _TopIcon extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  const _TopIcon({required this.icon, required this.tooltip});
  @override
  Widget build(BuildContext context) {
    return IconButton(onPressed: () {}, icon: Icon(icon), tooltip: tooltip);
  }
}

class _TabsOperacion extends StatelessWidget {
  final Operacion value;
  final ValueChanged<Operacion> onChanged;
  const _TabsOperacion({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final items = const [
      (Operacion.venta, 'Venta'),
      (Operacion.alquiler, 'Alquiler'),
      (Operacion.temporal, 'Alquiler Temporal'),
      (Operacion.proyectos, 'Proyectos'),
    ];
    return Wrap(
      spacing: 10,
      children: items.map((e) {
        final selected = value == e.$1;
        return ChoiceChip(
          label: Text(e.$2),
          selected: selected,
          onSelected: (_) => onChanged(e.$1),
          selectedColor: Theme.of(context).colorScheme.primary.withOpacity(.22),
          backgroundColor: Colors.white.withOpacity(.14),
          labelStyle: const TextStyle(
            color: Colors.black,
            fontWeight: FontWeight.w600,
          ),
          shape: StadiumBorder(
            side: BorderSide(color: Colors.white.withOpacity(.35)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        );
      }).toList(),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback action;
  final String actionLabel;

  const _EmptyState({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.action,
    required this.actionLabel,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 32),
      children: [
        const SizedBox(height: 8),
        Center(
          child: Column(
            children: [
              Icon(icon, size: 48, color: Colors.black.withOpacity(.45)),
              const SizedBox(height: 10),
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 6),
              Text(
                subtitle,
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium?.copyWith(color: Colors.black54),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: action,
                icon: const Icon(Icons.refresh),
                label: Text(actionLabel),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
