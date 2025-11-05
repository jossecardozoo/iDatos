import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# Rutas
CSV_PATH  = "datos_transformados_final.csv"
GPKG_PARADAS_PATH = "../datos/proximidadparadas.gpkg"
GPKG_BICI_PATH    = "../datos/proximidadbicircuito.gpkg"
OUT_PATH  = "propiedades_con_distancias.csv"

# Layers y columnas con los datos a obtener
LAYER_PARADAS = "1102_distanciaparada_zonacensal"
COL_PARADAS   = "DistanciaParada_mean"

LAYER_BICI    = "1128_distanciabicircuito_zonacensal"
COL_BICI      = "DistanciaBicicircuito_mean"

def main():
    # Propiedades -> GeoDataFrame
    props = pd.read_csv(CSV_PATH)
    props = props.dropna(subset=["latitud", "longitud"])
    props = props[(props["latitud"] != "N/A") & (props["longitud"] != "N/A")]
    props["latitud"] = props["latitud"].astype(float)
    props["longitud"] = props["longitud"].astype(float)
    props_gdf = gpd.GeoDataFrame(
        props, geometry=[Point(xy) for xy in zip(props["longitud"], props["latitud"])],
        crs="EPSG:4326"
    )

    # Zonas paradas 
    zonas_par = gpd.read_file(GPKG_PARADAS_PATH, layer=LAYER_PARADAS)[["geometry", COL_PARADAS]]
    if zonas_par.crs is None: zonas_par = zonas_par.set_crs("EPSG:4326")
    if zonas_par.crs != props_gdf.crs: zonas_par = zonas_par.to_crs(props_gdf.crs)

    # Zonas bici 
    zonas_bici = gpd.read_file(GPKG_BICI_PATH, layer=LAYER_BICI)[["geometry", COL_BICI]]
    if zonas_bici.crs is None: zonas_bici = zonas_bici.set_crs("EPSG:4326")
    if zonas_bici.crs != props_gdf.crs: zonas_bici = zonas_bici.to_crs(props_gdf.crs)

    # Join espacial
    j_par = gpd.sjoin(props_gdf, zonas_par, how="left", predicate="within")
    j_bici = gpd.sjoin(props_gdf, zonas_bici, how="left", predicate="within")

    # Salida
    out = props.copy()
    out["distancia_parada"] = j_par[COL_PARADAS]
    out["distancia_bicicircuito"] = j_bici[COL_BICI]
    out.to_csv(OUT_PATH, index=False)
    print(f"✅ Generado: {OUT_PATH}")

if __name__ == "__main__":
    main()
