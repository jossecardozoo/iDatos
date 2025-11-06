"""
Módulo de trazabilidad (Provenance) para tracking completo de transformaciones.

Implementa data provenance siguiendo principios FAIR:
- Findable: cada operación tiene metadata única
- Accessible: logs y metadatos almacenados
- Interoperable: formato estándar JSON
- Reusable: información completa para reproducibilidad
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import hashlib
import pandas as pd

from prefect import get_run_logger
try:
    from prefect.context import get_run_context
except ImportError:
    # Para versiones más antiguas de Prefect
    def get_run_context():
        try:
            from prefect import context
            return context
        except ImportError:
            return None


class ProvenanceTracker:
    """Rastrea la procedencia y transformaciones de datos."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("data/provenance")
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.current_run_id = None
        self.run_metadata = {}
    
    def start_run(self, flow_name: str, **kwargs) -> str:
        """Inicia un nuevo run y retorna su ID."""
        try:
            
            ctx = get_run_context()
            if hasattr(ctx, 'flow_run'):
                self.current_run_id = str(ctx.flow_run.id)
            elif hasattr(ctx, 'task_run'):
                self.current_run_id = str(ctx.task_run.flow_run_id)
        except Exception:
            pass
        
        if not self.current_run_id:
            timestamp = datetime.now(timezone.utc).isoformat()
            run_hash = hashlib.md5(f"{flow_name}{timestamp}".encode()).hexdigest()[:8]
            self.current_run_id = f"{flow_name}_{run_hash}"
        
        self.run_metadata = {
            'run_id': self.current_run_id,
            'flow_name': flow_name,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'parameters': kwargs,
            'tasks': [],
            'statistics': {}
        }
        return self.current_run_id
    
    def log_task(
        self,
        task_name: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        execution_time: float = None,
        **metadata
    ):
        """Registra la ejecución de una tarea."""
        try:
            ctx = get_run_context()
            task_run_id = None
            if hasattr(ctx, 'task_run'):
                task_run_id = str(ctx.task_run.id)
        except Exception:
            pass
        
        task_record = {
            'task_name': task_name,
            'task_run_id': task_run_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'input': input_data,
            'output': output_data,
            'execution_time_seconds': execution_time,
            **metadata
        }
        
        self.run_metadata['tasks'].append(task_record)
        
        logger = get_run_logger()
        logger.info(f"[Provenance] Task {task_name} logged: {json.dumps(output_data, default=str)}")
    
    def log_data_transformation(
        self,
        operation: str,
        source_file: str,
        rows_before: int,
        rows_after: int,
        columns_added: List[str] = None,
        columns_removed: List[str] = None,
        filters_applied: Dict[str, Any] = None,
        **metadata
    ):
        """Registra una transformación de datos."""
        transformation = {
            'operation': operation,
            'source_file': source_file,
            'rows_before': rows_before,
            'rows_after': rows_after,
            'rows_filtered': rows_before - rows_after,
            'columns_added': columns_added or [],
            'columns_removed': columns_removed or [],
            'filters_applied': filters_applied or {},
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **metadata
        }
        
        if 'transformations' not in self.run_metadata:
            self.run_metadata['transformations'] = []
        self.run_metadata['transformations'].append(transformation)
    
    def log_duplicate_detection(
        self,
        source: str,
        total_rows: int,
        duplicates_found: int,
        method: str,
        similarity_threshold: float,
        **metadata
    ):
        """Registra detección de duplicados."""
        dup_record = {
            'source': source,
            'total_rows': total_rows,
            'duplicates_found': duplicates_found,
            'unique_rows': total_rows - duplicates_found,
            'method': method,
            'similarity_threshold': similarity_threshold,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **metadata
        }
        
        if 'duplicate_detections' not in self.run_metadata:
            self.run_metadata['duplicate_detections'] = []
        self.run_metadata['duplicate_detections'].append(dup_record)
    
    def update_statistics(self, **stats):
        """Actualiza estadísticas del run."""
        self.run_metadata['statistics'].update(stats)
    
    def end_run(self, status: str = 'completed', error: Optional[str] = None):
        """Finaliza el run y guarda metadata."""
        self.run_metadata['ended_at'] = datetime.now(timezone.utc).isoformat()
        self.run_metadata['status'] = status
        if error:
            self.run_metadata['error'] = str(error)
        
        # Calcular duración
        if 'started_at' in self.run_metadata:
            start = datetime.fromisoformat(self.run_metadata['started_at'].replace('Z', '+00:00'))
            end = datetime.now(timezone.utc)
            duration = (end - start).total_seconds()
            self.run_metadata['duration_seconds'] = duration
        
        # Guardar a archivo
        if self.current_run_id:
            metadata_file = self.db_path / f"{self.current_run_id}_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.run_metadata, f, indent=2, default=str)
            
            logger = get_run_logger()
            logger.info(f"[Provenance] Run metadata saved to {metadata_file}")
    
    def get_run_summary(self) -> Dict[str, Any]:
        """Retorna un resumen del run actual."""
        return {
            'run_id': self.current_run_id,
            'flow_name': self.run_metadata.get('flow_name'),
            'status': self.run_metadata.get('status', 'running'),
            'tasks_count': len(self.run_metadata.get('tasks', [])),
            'statistics': self.run_metadata.get('statistics', {})
        }


# Instancia global del tracker
_provenance_tracker = None


def get_provenance_tracker() -> ProvenanceTracker:
    """Obtiene o crea la instancia global del tracker."""
    global _provenance_tracker
    if _provenance_tracker is None:
        _provenance_tracker = ProvenanceTracker()
    return _provenance_tracker


def track_data_hash(df: pd.DataFrame) -> str:
    """Calcula hash de un DataFrame para tracking de cambios."""
    # Usar solo los valores (sin índices) para el hash
    values_str = df.values.tobytes() if hasattr(df.values, 'tobytes') else str(df.values)
    columns_str = ','.join(sorted(df.columns))
    content = f"{columns_str}|{values_str}"
    return hashlib.md5(content.encode()).hexdigest()

