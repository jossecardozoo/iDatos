from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import json

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
    coords: tuple[float, float] = Field(..., description="(lat, lon)")
    precioUYU: Optional[float] = None

# El path del json donde saca la información sobre las propiedades
DATA_PATH = Path(__file__).resolve().parent / "listings.json"
with DATA_PATH.open("r", encoding="utf-8") as f:
    DATA: List[Propiedad] = [Propiedad(**x) for x in json.load(f)]

# Obtener todas las propiedades 
@app.get("/datos", response_model=List[Propiedad])
def listar_datos(skip: int = 0, limit: int = 50):
    return DATA[skip : skip + limit]

# Obtener una propiedad especifica en base al id
@app.get("/datos/{id}", response_model=Propiedad)
def obtener_propiedad(id: str):
    for it in DATA:
        if it.id == id:
            return it
    raise HTTPException(status_code=404, detail="No encontrado")
