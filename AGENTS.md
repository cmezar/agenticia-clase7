# Reglas del proyecto

## Agentes

- Los agentes viven en `src/{nombre_agente}/`.
- Cada agente debe tener `graph.py`, `prompts.py` y `tools.py` (además de un `__init__.py` vacío).
- Cada nodo debe tener su propio prompt en `prompts.py`; no pongas reglas de comportamiento dentro de `graph.py`.
- Los prompts son constantes y las tools solo deben contener definiciones de tools.
- Se ejecutan desde la raíz con:

  ```powershell
  python main.py {nombre_agente} "mensaje"
  ```

- `--saltos` imprime los nodos por los que pasó el grafo.
- `--diagrama` imprime el Mermaid del grafo sin ejecutar el grafo ni requerir API key.

## API y scripts

- La API vive en `api/app.py` y se levanta con:

  ```powershell
  uvicorn api.app:app --reload --port 8000
  ```

- Los scripts sueltos van en `scripts/`.
- Las pruebas van en `tests/` y se ejecutan con `pytest`.

## Despliegue

- `Procfile` debe contener: `web: uvicorn api.app:app --host 0.0.0.0 --port $PORT`.
- `.python-version` debe indicar `3.12`.
- `requirements.txt` debe mantenerse siempre actualizado.
- No se deben commitear secretos ni valores reales de configuración.
