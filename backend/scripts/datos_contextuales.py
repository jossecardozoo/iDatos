from pathlib import Path
import pandas as pd

def enrich_with_contextual_data(df: pd.DataFrame,
                                 gpkg_paradas: str | Path = Path('datos') / 'proximidadparadas.gpkg',
                                 gpkg_bici: str | Path = Path('datos') / 'proximidadbicircuito.gpkg',
                                 layer_paradas: str = '1102_distanciaparada_zonacensal',
                                 col_paradas: str = 'DistanciaParada_mean',
                                 layer_bici: str = '1128_distanciabicircuito_zonacensal',
                                 col_bici: str = 'DistanciaBicicircuito_mean',
                                 logger=None) -> pd.DataFrame:
    """Enrich a DataFrame (backend copy) with contextual distance fields using geopandas layers.

    This mirrors the behavior of the repo-root helper but uses relative gpkg paths appropriate for backend cwd.
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except Exception:
        if logger:
            logger.info('geopandas no disponible -- saltando enrich_with_contextual_data (backend)')
        return df

    try:
        df2 = df.copy()
        if 'latitud' not in df2.columns or 'longitud' not in df2.columns:
            if logger:
                logger.info('DataFrame no tiene columnas latitud/longitud -- skip contextual enrichment')
            return df2
        df2 = df2.dropna(subset=['latitud', 'longitud'])
        df2 = df2[(df2['latitud'] != 'N/A') & (df2['longitud'] != 'N/A')]
        df2['latitud'] = df2['latitud'].astype(float)
        df2['longitud'] = df2['longitud'].astype(float)

        props_gdf = gpd.GeoDataFrame(
            df2, geometry=[Point(xy) for xy in zip(df2['longitud'], df2['latitud'])], crs='EPSG:4326'
        )

        gpkg_paradas = Path(gpkg_paradas)
        gpkg_bici = Path(gpkg_bici)
        distancia_parada = None
        distancia_bici = None

        if gpkg_paradas.exists():
            try:
                zonas_par = gpd.read_file(gpkg_paradas, layer=layer_paradas)[['geometry', col_paradas]]
                if zonas_par.crs is None:
                    zonas_par = zonas_par.set_crs('EPSG:4326')
                if zonas_par.crs != props_gdf.crs:
                    zonas_par = zonas_par.to_crs(props_gdf.crs)
                j_par = gpd.sjoin(props_gdf, zonas_par, how='left', predicate='within')
                distancia_parada = j_par[col_paradas]
            except Exception as e:
                if logger:
                    logger.info(f'error leyendo capas paradas: {e}')

        if gpkg_bici.exists():
            try:
                zonas_bici = gpd.read_file(gpkg_bici, layer=layer_bici)[['geometry', col_bici]]
                if zonas_bici.crs is None:
                    zonas_bici = zonas_bici.set_crs('EPSG:4326')
                if zonas_bici.crs != props_gdf.crs:
                    zonas_bici = zonas_bici.to_crs(props_gdf.crs)
                j_bici = gpd.sjoin(props_gdf, zonas_bici, how='left', predicate='within')
                distancia_bici = j_bici[col_bici]
            except Exception as e:
                if logger:
                    logger.info(f'error leyendo capas bici: {e}')

        out = df.copy()
        out['distancia_parada'] = None
        out['distancia_bicicircuito'] = None
        if distancia_parada is not None:
            try:
                out.loc[df2.index, 'distancia_parada'] = distancia_parada.values
            except Exception:
                out['distancia_parada'] = distancia_parada.values
        if distancia_bici is not None:
            try:
                out.loc[df2.index, 'distancia_bicicircuito'] = distancia_bici.values
            except Exception:
                out['distancia_bicicircuito'] = distancia_bici.values
        return out
    except Exception as e:
        if logger:
            logger.info(f'error en enrich_with_contextual_data (backend): {e}')
        return df


if __name__ == '__main__':
    import pandas as pd
    CSV_PATH = 'datos_transformados_final.csv'
    OUT_PATH = 'propiedades_con_distancias.csv'
    try:
        props = pd.read_csv(CSV_PATH)
        out = enrich_with_contextual_data(props)
        out.to_csv(OUT_PATH, index=False)
        print(f'✅ Generado: {OUT_PATH}')
    except Exception as e:
        print('Error:', e)
