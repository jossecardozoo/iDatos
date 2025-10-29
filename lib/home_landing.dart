import 'package:flutter/material.dart';
import 'listings_page.dart';

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
          'MONTEROOM',
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w800,
          ),
        ),
        actions: [
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.person_outline),
            tooltip: 'Perfil',
          ),
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.map_outlined),
            tooltip: 'Mapa',
          ),
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.help_outline),
            tooltip: 'Ayuda',
          ),
          const SizedBox(width: 8),
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
                colors: [Color(0xFF103C49), Color(0xFF0B4F59)], // teal oscuro
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
                        onChanged: (v) => setState(() => op = v),
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
                                  onChanged: (v) => setState(
                                    () => _tipoProp = v ?? _tipoProp,
                                  ),
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
                                ),
                              ),
                              const SizedBox(width: 10),

                              // Botón Buscar coral
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
          const Expanded(child: SizedBox()),
        ],
      ),
    );
  }

  void _onBuscar() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ListingsPage(
          initialQuery: _ubicacionCtrl.text.trim().isEmpty
              ? null
              : _ubicacionCtrl.text.trim(),
          initialTipoOperacion: op,
          initialTipoPropiedad: _tipoProp,
        ),
      ),
    );
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
