class Indicadores {
  final int? paradasCercanas;
  final int? seguridadScore;
  final int? hospitalesCerca;
  final int? escuelasCerca;
  final int? supermercadosCerca;
  final int? plazasCerca;

  const Indicadores({
    this.paradasCercanas,
    this.seguridadScore,
    this.hospitalesCerca,
    this.escuelasCerca,
    this.supermercadosCerca,
    this.plazasCerca,
  });

  factory Indicadores.fromJson(Map<String, dynamic> j) => Indicadores(
    paradasCercanas: j['paradasCercanas'] as int?,
    seguridadScore: j['seguridadScore'] as int?,
    hospitalesCerca: j['hospitalesCerca'] as int?,
    escuelasCerca: j['escuelasCerca'] as int?,
    supermercadosCerca: j['supermercadosCerca'] as int?,
    plazasCerca: j['plazasCerca'] as int?,
  );
}

class Listing {
  final String id;
  final String titulo;
  final String fuente;
  final String url;
  final String? barrio;
  final double? precioUYU;
  final double? precioUSD;
  final double? sup;
  final int? dorms;
  final List<double> coords;
  final String tipo;
  final Indicadores? indicadores;

  Listing({
    required this.id,
    required this.titulo,
    required this.fuente,
    required this.url,
    this.barrio,
    this.precioUYU,
    this.precioUSD,
    this.sup,
    this.dorms,
    required this.coords,
    required this.tipo,
    this.indicadores,
  });

  factory Listing.fromJson(Map<String, dynamic> j) => Listing(
    id: j['id'] as String,
    titulo: j['titulo'] as String,
    fuente: j['fuente'] as String,
    url: j['url'] as String,
    barrio: j['barrio'] as String?,
    precioUYU: (j['precioUYU'] as num?)?.toDouble(),
    precioUSD: (j['precioUSD'] as num?)?.toDouble(),
    sup: (j['sup'] as num?)?.toDouble(),
    dorms: j['dorms'] as int?,
    indicadores: j['indicadores'] != null
        ? Indicadores.fromJson(j['indicadores'] as Map<String, dynamic>)
        : null,
    coords: (j['coords'] as List).map((e) => (e as num).toDouble()).toList(),
    tipo: j['tipo'] as String,
  );
}
