import 'dart:convert';
import 'package:flutter/services.dart' show rootBundle;
import 'listing.dart';
import 'home_landing.dart';
import 'package:http/http.dart' as http;

class ListingRepository {
  // Url base donde se expone el backend
  static const String _baseUrl = 'http://127.0.0.1:8001';

  Future<List<Listing>> getAll({
    String? q,
    Operacion? tipoOperacion,
    String? tipoPropiedad,
  }) async {
    // Url para poder obtener los datos del backend
    final uri = Uri.parse('$_baseUrl/datos?skip=0&limit=500');

    final res = await http.get(uri);
    if (res.statusCode != 200) {
      throw Exception('API error: ${res.statusCode} - ${res.body}');
    }

    final list = (jsonDecode(res.body) as List)
        .map((e) => Listing.fromJson(e as Map<String, dynamic>))
        .toList();

    return list.where((l) {
      final okQ =
          q == null ||
          l.titulo.toLowerCase().contains(q.toLowerCase()) ||
          (l.barrio ?? '').toLowerCase().contains(q.toLowerCase());
      final okOp =
          tipoOperacion == null ||
          (tipoOperacion == Operacion.alquiler && l.tipo == 'alquiler') ||
          (tipoOperacion == Operacion.venta && l.tipo == 'venta') ||
          (tipoOperacion == Operacion.temporal && l.tipo == 'temporal') ||
          (tipoOperacion == Operacion.proyectos);

      final okTipoProp =
          tipoPropiedad == null ||
          l.titulo.toLowerCase().contains(tipoPropiedad.toLowerCase());

      return okQ && okOp && okTipoProp;
    }).toList();
  }
}
