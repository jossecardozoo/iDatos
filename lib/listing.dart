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

// listing.dart
class Listing {
  final String id;
  final String titulo;
  final String tipo;
  final double lat;
  final double lon;

  final double? precioUYU;
  final double? dorms;
  final double? banos;
  final String? imagenUrl;

  final String? barrio;

  Listing({
    required this.id,
    required this.titulo,
    required this.tipo,
    required this.lat,
    required this.lon,
    this.precioUYU,
    this.dorms,
    this.banos,
    this.imagenUrl,
    this.barrio,
  });

  factory Listing.fromJson(Map<String, dynamic> j) {
    final coords = (j['coords'] as List).cast<num>();
    return Listing(
      id: j['id'] as String,
      titulo: j['titulo'] as String,
      tipo: j['tipo'] as String,
      lat: coords[0].toDouble(),
      lon: coords[1].toDouble(),
      precioUYU: (j['precioUYU'] as num?)?.toDouble(),
      dorms: (j['dorms'] as num?)?.toDouble(),
      banos: (j['banos'] as num?)?.toDouble(),
      imagenUrl: j['imagen_url'] as String?,
      barrio: j['barrio'] as String?,
    );
  }
}
