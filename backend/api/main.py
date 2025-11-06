from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import pandas as pd
import sqlite3
import hashlib
import math

from pathlib import Path

API_DIR = Path(__file__).resolve().parent
DB_PATH = API_DIR.parent / "data" / "etl_datalake.db"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Propiedad(BaseModel):
    id: str
    titulo: str
    tipo: str
    coords: tuple[float, float]
    precioUYU: Optional[float] = None
    dorms: Optional[float] = None
    banos: Optional[float] = None
    imagen_url: Optional[str] = None
    barrio: Optional[str] = None
    distancia_parada: Optional[float] = None
    distancia_bicicircuito: Optional[float] = None
    nivel_criminalidad: Optional[str] = None


def inferir_tipo(source_file: Optional[str]) -> str:
    if not source_file:
        return "desconocido"
    sf = source_file.lower()
    if "alquiler" in sf:
        return "alquiler"
    if "venta" in sf:
        return "venta"
    return "desconocido"


def hacer_id_unico(
    titulo: str, ubicacion: Optional[str], precio_valor_num: Optional[float]
) -> str:
    base = f"{titulo}|{ubicacion or ''}|{precio_valor_num or ''}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _none_if_nan(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def cargar_propiedades_desde_sqlite(db_path: Path) -> List[Propiedad]:
    if not db_path.exists():
        raise RuntimeError(f"No se encontró la base de datos en: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        query = """
            SELECT
              titulo,
              ubicacion,
              precio_base_uyu,
              latitud,
              longitud,
              source_file,
              precio_valor_num,
              dorms,
              banos,
              imagen_url,
              barrio_guess,
              distancia_parada,
              distancia_bicicircuito,
              nivel_criminalidad
            FROM transformed_listings
        """
        df = pd.read_sql_query(query, conn)

    props: List[Propiedad] = []
    for _, row in df.iterrows():
        lat, lon = row.get("latitud"), row.get("longitud")
        if pd.isna(lat) or pd.isna(lon):
            continue

        prop = Propiedad(
            id=hacer_id_unico(
                titulo=str(row.get("titulo") or ""),
                ubicacion=row.get("ubicacion"),
                precio_valor_num=(
                    None
                    if pd.isna(row.get("precio_valor_num"))
                    else float(row.get("precio_valor_num"))
                ),
            ),
            titulo=str(row.get("titulo") or "").strip(),
            tipo=inferir_tipo(row.get("source_file")),
            coords=(float(lat), float(lon)),
            precioUYU=(
                None
                if pd.isna(row.get("precio_base_uyu"))
                else float(row.get("precio_base_uyu"))
            ),
            dorms=_none_if_nan(row.get("dorms")),
            banos=_none_if_nan(row.get("banos")),
            imagen_url=(
                str(row.get("imagen_url")).strip()
                if not pd.isna(row.get("imagen_url"))
                else None
            ),
            barrio=row.get("barrio_guess"),
            distancia_parada=_none_if_nan(row.get("distancia_parada")),
            distancia_bicicircuito=_none_if_nan(row.get("distancia_bicicircuito")),
            nivel_criminalidad=row.get("nivel_criminalidad"),
        )
        props.append(prop)

    return props


DATA: List[Propiedad] = cargar_propiedades_desde_sqlite(DB_PATH)


@app.get("/datos", response_model=List[Propiedad])
def listar_datos(skip: int = 0, limit: int = 50):
    return DATA[skip : skip + limit]


@app.get("/datos/{id}", response_model=Propiedad)
def obtener_propiedad(id: str):
    for it in DATA:
        if it.id == id:
            return it
    raise HTTPException(status_code=404, detail="No encontrado")
