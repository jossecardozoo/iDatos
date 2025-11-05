// listing_repository.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'listing.dart';
import 'home_landing.dart';

class ListingRepository {
  static const String _baseUrl = 'http://127.0.0.1:8001';

  Future<List<Listing>> getAll({
    String? q,
    Operacion? tipoOperacion,
    String? tipoPropiedad,
  }) async {
    final uri = Uri.parse('$_baseUrl/datos?skip=0&limit=500');
    final res = await http.get(uri);
    if (res.statusCode != 200) {
      throw Exception('API error: ${res.statusCode} - ${res.body}');
    }

    final list = (jsonDecode(res.body) as List)
        .map((e) => Listing.fromJson(e as Map<String, dynamic>))
        .toList();

    return list.where((l) {
      final qLower = q?.toLowerCase();
      final okQ =
          q == null ||
          l.titulo.toLowerCase().contains(qLower!) ||
          (l.barrio ?? '').toLowerCase().contains(qLower);

      final okOp =
          tipoOperacion == null ||
          (tipoOperacion == Operacion.alquiler && l.tipo == 'alquiler') ||
          (tipoOperacion == Operacion.venta && l.tipo == 'venta') ||
          (tipoOperacion == Operacion.temporal) ||
          (tipoOperacion == Operacion.proyectos);

      final okTipoProp =
          tipoPropiedad == null ||
          l.titulo.toLowerCase().contains(tipoPropiedad.toLowerCase());

      return okQ && okOp && okTipoProp;
    }).toList();
  }
}
