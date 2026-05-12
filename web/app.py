"""Mathesis Web Transport — FastAPI application.

Thin wrapper over MathesisDB. Renders HTML pages with KaTeX for math.
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root to path for mathesis imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import MathesisDB, EntityNotFoundError

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Mathesis", docs_url=None, redoc_url=None)

WEB_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

DB_PATH = PROJECT_ROOT / "mathesis_index.db"
kb = MathesisDB(str(DB_PATH))


@app.on_event("startup")
def startup():
    kb.connect()


@app.on_event("shutdown")
def shutdown():
    kb.close()


# ---------------------------------------------------------------------------
# Entity type metadata for templates
# ---------------------------------------------------------------------------

ENTITY_TYPES = {
    "axiom":     {"name_ru": "Аксиомы",   "icon": "A", "color": "#e74c3c"},
    "object":    {"name_ru": "Объекты",    "icon": "O", "color": "#3498db"},
    "property":  {"name_ru": "Свойства",   "icon": "P", "color": "#2ecc71"},
    "operation": {"name_ru": "Операции",   "icon": "Op","color": "#f39c12"},
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Homepage: all entities grouped by type."""
    axioms = kb.list_axioms()
    objects = kb.list_objects()
    properties = kb.list_properties()
    operations = kb.list_operations()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "axioms": axioms,
        "objects": objects,
        "properties": properties,
        "operations": operations,
        "types": ENTITY_TYPES,
    })


@app.get("/axioms/{id}", response_class=HTMLResponse)
async def axiom_page(request: Request, id: str):
    try:
        entity = kb.get_axiom(id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Axiom '{id}' not found")

    used_by = kb.get_used_by(id)

    return templates.TemplateResponse("entity.html", {
        "request": request,
        "entity": entity,
        "entity_type": "axiom",
        "meta": ENTITY_TYPES["axiom"],
        "used_by": used_by,
        "extra": {"system": entity.system},
    })


@app.get("/objects/{id}", response_class=HTMLResponse)
async def object_page(request: Request, id: str):
    try:
        entity = kb.get_object(id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Object '{id}' not found")

    props = kb.get_object_properties(id)
    used_by = kb.get_used_by(id)

    # Resolve property names
    prop_details = []
    for p in props:
        try:
            prop_obj = kb.get_property(p.property_id)
            prop_details.append({
                "id": p.property_id,
                "name": prop_obj.name,
                "context": p.context,
            })
        except EntityNotFoundError:
            pass

    return templates.TemplateResponse("entity.html", {
        "request": request,
        "entity": entity,
        "entity_type": "object",
        "meta": ENTITY_TYPES["object"],
        "used_by": used_by,
        "extra": {
            "intuition": entity.intuition,
            "aliases": entity.aliases,
            "properties": prop_details,
        },
    })


@app.get("/properties/{id}", response_class=HTMLResponse)
async def property_page(request: Request, id: str):
    try:
        entity = kb.get_property(id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Property '{id}' not found")

    used_by = kb.get_used_by(id)

    return templates.TemplateResponse("entity.html", {
        "request": request,
        "entity": entity,
        "entity_type": "property",
        "meta": ENTITY_TYPES["property"],
        "used_by": used_by,
        "extra": {
            "aliases": entity.aliases,
            "equivalent_forms": entity.equivalent_forms,
        },
    })


@app.get("/operations/{id}", response_class=HTMLResponse)
async def operation_page(request: Request, id: str):
    try:
        entity = kb.get_operation(id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Operation '{id}' not found")

    args = kb.get_operation_arguments(id)
    used_by = kb.get_used_by(id)

    # Resolve argument object names
    arg_details = []
    for a in args:
        try:
            obj = kb.get_object(a.object_id)
            arg_details.append({
                "position": a.position,
                "object_name": obj.name,
                "object_id": a.object_id,
                "role": a.role,
            })
        except EntityNotFoundError:
            pass

    codomain_name = None
    if entity.codomain_id:
        try:
            codomain_name = kb.get_object(entity.codomain_id).name
        except EntityNotFoundError:
            pass

    return templates.TemplateResponse("entity.html", {
        "request": request,
        "entity": entity,
        "entity_type": "operation",
        "meta": ENTITY_TYPES["operation"],
        "used_by": used_by,
        "extra": {
            "aliases": entity.aliases,
            "arity": entity.arity,
            "arguments": arg_details,
            "codomain_id": entity.codomain_id,
            "codomain_name": codomain_name,
        },
    })
