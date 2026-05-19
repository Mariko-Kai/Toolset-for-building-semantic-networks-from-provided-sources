"""Mathesis Web Transport — FastAPI application.

Thin wrapper over MathesisDB. Renders HTML pages with KaTeX for math.
"""

import os
import sys
import threading
import re
import asyncio
import subprocess
import atexit
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root to path for mathesis imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import MathesisDB, EntityNotFoundError

# ---------------------------------------------------------------------------
# Compiler Global State (for multiplayer sync)
# ---------------------------------------------------------------------------

class CompilerState:
    def __init__(self):
        self.is_compiling = False
        self.root_entity = "thm-cauchy-criterion-limit-base"
        self.query = "Определи интеграл Римана"
        self.mode = "query"
        self.logs = []

state = CompilerState()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Mathesis", docs_url=None, redoc_url=None)

app.state.cloudflare_url = None
app.state.cloudflared_process = None

WEB_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

DB_PATH = PROJECT_ROOT / "mathesis_index.db"
kb = MathesisDB(str(DB_PATH))


def start_cloudflare_tunnel():
    cloudflared_exe = PROJECT_ROOT / "tools" / "cloudflared.exe"
    if not cloudflared_exe.exists():
        print(f"[cloudflared] Executable not found at {cloudflared_exe}")
        return
        
    cmd = [str(cloudflared_exe), "tunnel", "--url", "http://127.0.0.1:8000"]
    print(f"[cloudflared] Starting tunnel: {' '.join(cmd)}")
    
    # Start process and redirect stderr to stdout
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(PROJECT_ROOT),
        **kwargs
    )
    app.state.cloudflared_process = process
    
    # Read output to find trycloudflare URL
    for line in iter(process.stdout.readline, ""):
        print(f"[cloudflared] {line.strip()}")
        # Search for trycloudflare.com URL
        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
        if match:
            url = match.group(0)
            app.state.cloudflare_url = url
            print(f"[cloudflared] Captured public URL: {url}")
            # Broadcast the new URL if sockets are active
            if main_loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "cloudflare_url", "url": url}),
                    main_loop
                )
            
    process.stdout.close()
    process.wait()


main_loop = None

@app.on_event("startup")
def startup():
    global main_loop
    kb.connect()
    main_loop = asyncio.get_event_loop()
    # Start Cloudflare Tunnel automatically in a background thread
    tunnel_thread = threading.Thread(target=start_cloudflare_tunnel, daemon=True)
    tunnel_thread.start()


@app.on_event("shutdown")
def shutdown():
    kb.close()
    cleanup_tunnel()


def cleanup_tunnel():
    if hasattr(app.state, "cloudflared_process") and app.state.cloudflared_process:
        if app.state.cloudflared_process.poll() is None:
            print("[cloudflared] Terminating tunnel process...")
            try:
                app.state.cloudflared_process.terminate()
                app.state.cloudflared_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                print("[cloudflared] Process did not terminate, killing...")
                try:
                    app.state.cloudflared_process.kill()
                except Exception:
                    pass
            except Exception:
                pass
        app.state.cloudflared_process = None


atexit.register(cleanup_tunnel)


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
    """Homepage: PDF compiler page."""
    try:
        axioms = kb.list_axioms()
        objects = kb.list_objects()
        properties = kb.list_properties()
        operations = kb.list_operations()
    except Exception:
        axioms, objects, properties, operations = [], [], [], []
        
    all_entity_ids = []
    for a in axioms: all_entity_ids.append(a.id)
    for o in objects: all_entity_ids.append(o.id)
    for p in properties: all_entity_ids.append(p.id)
    for op in operations: all_entity_ids.append(op.id)
    all_entity_ids.sort()

    return templates.TemplateResponse("compiler.html", {
        "request": request,
        "entity_ids": all_entity_ids,
        "cloudflare_url": app.state.cloudflare_url,
    })


@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):
    """Catalog page: all entities grouped by type."""
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


# ---------------------------------------------------------------------------
# WebSocket Connection Manager & Async Compilation
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


async def run_compilation_async(mode: str, value: str):
    state.is_compiling = True
    state.mode = mode
    state.logs = []
    
    if mode == "id":
        state.root_entity = value
        cmd = [sys.executable, str(PROJECT_ROOT / "pipeline" / "generate_answer.py"), "--root", value]
    else:
        state.query = value
        cmd = [sys.executable, str(PROJECT_ROOT / "pipeline" / "ollama_wrapper.py"), value]
        
    # Broadcast that compilation has started to all connected sessions
    await manager.broadcast({
        "type": "start",
        "mode": mode,
        "value": value
    })
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT)
        )
        
        # Read lines asynchronously as they are written by the compiler script
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='replace').rstrip('\r\n')
            state.logs.append(decoded_line)
            # Send log line to all connected clients
            await manager.broadcast({
                "type": "log",
                "line": decoded_line
            })
            
        await process.wait()
    except Exception as e:
        err_msg = f"[System Error] Compilation process failed: {str(e)}"
        state.logs.append(err_msg)
        await manager.broadcast({
            "type": "log",
            "line": err_msg
        })
        
    state.is_compiling = False
    # Send compilation complete signal to all clients
    await manager.broadcast({
        "type": "done"
    })


@app.get("/compiler")
async def compiler_page_redirect():
    return RedirectResponse(url="/")


@app.get("/result.pdf")
async def get_result_pdf():
    pdf_path = PROJECT_ROOT / "result.pdf"
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")
    else:
        raise HTTPException(status_code=404, detail="result.pdf not found")


@app.get("/master.pdf")
async def get_master_pdf():
    pdf_path = PROJECT_ROOT / "master.pdf"
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")
    else:
        raise HTTPException(status_code=404, detail="master.pdf not found")


@app.websocket("/ws/compiler")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Immediately send the current status of the compiler to the newly connected user
    await websocket.send_json({
        "type": "init",
        "root": state.root_entity,
        "query": state.query,
        "mode": state.mode,
        "is_compiling": state.is_compiling,
        "logs": state.logs,
        "cloudflare_url": app.state.cloudflare_url
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "input":
                # User typed something -> sync search text on all devices in real-time
                state.mode = data["mode"]
                if data["mode"] == "id":
                    state.root_entity = data["value"]
                else:
                    state.query = data["value"]
                await manager.broadcast({
                    "type": "input",
                    "mode": state.mode,
                    "value": data["value"]
                })
                
            elif data["type"] == "start":
                # User clicked "Compile" -> trigger build if not already running
                if not state.is_compiling:
                    asyncio.create_task(run_compilation_async(data["mode"], data["value"]))
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket)

