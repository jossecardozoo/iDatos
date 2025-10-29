import 'dart:convert';
import 'package:flutter/services.dart' show rootBundle;
import 'listing.dart';
import 'home_landing.dart';

class ListingRepository {
  Future<List<Listing>> getAll({
    String? q,
    Operacion? tipoOperacion,
    String? tipoPropiedad,
  }) async {
    final raw = await rootBundle.loadString('assets/data/listings.json');
    final list = (jsonDecode(raw) as List)
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
