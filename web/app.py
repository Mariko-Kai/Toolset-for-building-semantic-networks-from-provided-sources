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
import json
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root to path for mathesis imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import MathesisDB, EntityNotFoundError
from pipeline.logging_utils import normalize_pipeline_log_line as normalize_pipeline_stdout

# ---------------------------------------------------------------------------
# Compiler Global State (for multiplayer sync)
# ---------------------------------------------------------------------------

class CompilerState:
    def __init__(self):
        self.is_compiling = False
        self.cancel_requested = False
        self.current_process = None
        self.process_lock = threading.Lock()
        self.root_entity = "thm-cauchy-criterion-limit-base"
        self.query = "Определи интеграл Римана"
        self.mode = "query"
        self.logs = []

state = CompilerState()
api_config = None

def load_or_create_api_config():
    config_path = PROJECT_ROOT / "api_config.json"
    
    # 1. Fetch defaults from pipeline.config
    try:
        from pipeline.config import get_default_provider, get_default_model
        default_config = {
            "api_keys": {
                "gemini": "",
                "openai": "",
                "groq": ""
            },
            "providers": {
                "extract": get_default_provider("extract"),
                "synth": get_default_provider("synth"),
                "lean": get_default_provider("lean"),
                "preview": get_default_provider("preview"),
            },
            "models": {
                "extract": get_default_model("extract", get_default_provider("extract")),
                "synth": get_default_model("synth", get_default_provider("synth")),
                "lean": get_default_model("lean", get_default_provider("lean")),
                "preview": get_default_model("preview", get_default_provider("preview")),
            }
        }
    except Exception as e:
        print(f"[config] Failed to load defaults from pipeline.config: {e}")
        default_config = {
            "api_keys": {
                "gemini": "",
                "openai": "",
                "groq": ""
            },
            "providers": {
                "extract": "ollama",
                "synth": "ollama",
                "lean": "ollama",
                "preview": "llama_cpp"
            },
            "models": {
                "extract": "qwen3:8b",
                "synth": "qwen3:8b",
                "lean": "qwen3:8b",
                "preview": "bge-reranker-v2-m3-Q6_K.gguf"
            }
        }

    config = None
    if config_path.exists():
        try:
            content = config_path.read_text(encoding='utf-8').strip()
            if not content:
                print(f"[config] api_config.json is empty. Generating default configuration.")
            else:
                config = json.loads(content)
        except Exception as e:
            print(f"[config] Error reading/parsing api_config.json: {e}. Re-generating standard defaults.")
            
    if not config:
        config = default_config
        try:
            config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f"[config] Created default api_config.json at {config_path}")
        except Exception as e:
            print(f"[config] Failed to write default api_config.json: {e}")
    else:
        updated = False
        for sec in ["api_keys", "providers", "models"]:
            if sec not in config or not isinstance(config[sec], dict):
                config[sec] = default_config[sec]
                updated = True
            else:
                for k, v in default_config[sec].items():
                    if k not in config[sec]:
                        config[sec][k] = v
                        updated = True
        if updated:
            try:
                config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
                print(f"[config] Updated api_config.json with missing fields.")
            except Exception as e:
                print(f"[config] Failed to update api_config.json: {e}")

    keys = config.get("api_keys", {})
    if keys.get("gemini"):
        os.environ["GEMINI_API_KEY"] = keys["gemini"]
        os.environ["GOOGLE_API_KEY"] = keys["gemini"]
    if keys.get("openai"):
        os.environ["OPENAI_API_KEY"] = keys["openai"]
    if keys.get("groq"):
        os.environ["GROQ_API_KEY"] = keys["groq"]

    print("[config] Active API configuration:")
    for k, prov in config.get("providers", {}).items():
        model = config.get("models", {}).get(k, "")
        print(f"  - Module '{k}': provider = {prov}, model = {model}")
        
    return config

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Mathesis", docs_url=None, redoc_url=None)

app.state.cloudflare_url = None
app.state.cloudflared_process = None
app.state.cloudflared_job = None

WEB_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

DB_PATH = PROJECT_ROOT / "mathesis_index.db"
kb = MathesisDB(str(DB_PATH))


# ---------------------------------------------------------------------------
# Windows Job Objects for robust process lifecycle management
# ---------------------------------------------------------------------------
if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
    except Exception as e:
        print(f"[Windows Job Object] Failed to load kernel32 and declare signatures: {e}")


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
    
    if os.name == 'nt':
        try:
            hJob = kernel32.CreateJobObjectW(None, None)
            if hJob:
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                
                res = kernel32.SetInformationJobObject(
                    hJob,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info)
                )
                if res:
                    res_assign = kernel32.AssignProcessToJobObject(hJob, int(process._handle))
                    if res_assign:
                        app.state.cloudflared_job = hJob
                        print(f"[cloudflared] Successfully assigned process {process.pid} to Job Object.")
                    else:
                        print(f"[cloudflared] Failed to assign process to Job Object: {ctypes.WinError(ctypes.get_last_error())}")
                        kernel32.CloseHandle(hJob)
                else:
                    print(f"[cloudflared] Failed to set Job Object limit info: {ctypes.WinError(ctypes.get_last_error())}")
                    kernel32.CloseHandle(hJob)
        except Exception as e:
            print(f"[cloudflared] Error setting up Windows Job Object: {e}")
    
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
    global main_loop, api_config
    kb.connect()
    api_config = load_or_create_api_config()
    main_loop = asyncio.get_event_loop()
    # Start Cloudflare Tunnel automatically in a background thread
    tunnel_thread = threading.Thread(target=start_cloudflare_tunnel, daemon=True)
    tunnel_thread.start()


@app.on_event("shutdown")
def shutdown():
    cancel_running_compilation()
    kb.close()
    cleanup_tunnel()


def cleanup_tunnel():
    if os.name == 'nt' and hasattr(app.state, "cloudflared_job") and app.state.cloudflared_job:
        print("[cloudflared] Closing Job Object handle (killing all tunnel processes)...")
        try:
            kernel32.CloseHandle(app.state.cloudflared_job)
        except Exception as e:
            print(f"[cloudflared] Error closing Job Object: {e}")
        app.state.cloudflared_job = None
        app.state.cloudflared_process = None
        return

    if hasattr(app.state, "cloudflared_process") and app.state.cloudflared_process:
        process = app.state.cloudflared_process
        if process.poll() is None:
            print("[cloudflared] Terminating tunnel process...")
            try:
                if os.name == 'nt':
                    # Forcefully kill the entire process tree on Windows
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.terminate()
                    process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                print("[cloudflared] Process did not terminate, killing...")
                try:
                    process.kill()
                except Exception:
                    pass
            except Exception as e:
                print(f"[cloudflared] Error terminating process: {e}")
        app.state.cloudflared_process = None


atexit.register(cleanup_tunnel)


def set_current_compilation_process(process):
    with state.process_lock:
        state.current_process = process


def get_current_compilation_process():
    with state.process_lock:
        return state.current_process


def clear_current_compilation_process(process):
    with state.process_lock:
        if state.current_process is process:
            state.current_process = None


def terminate_process_tree(process, *, timeout=5):
    if not process or process.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
            return
        except Exception as e:
            print(f"[compiler] taskkill failed for process {process.pid}: {e}")
    else:
        try:
            os.killpg(process.pid, 15)
            process.wait(timeout=timeout)
            return
        except Exception as e:
            print(f"[compiler] process group terminate failed for process {process.pid}: {e}")

    try:
        process.kill()
    except Exception:
        pass


def cancel_running_compilation():
    if not state.is_compiling:
        return False

    state.cancel_requested = True
    process = get_current_compilation_process()
    if process and process.poll() is None:
        terminate_process_tree(process)
    return True


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
    cache_path = PROJECT_ROOT / "output" / "nl_translations_cache.json"
    cache_data = {}
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            try:
                cache_data = json.load(f)
            except json.JSONDecodeError:
                cache_data = {}

    axioms, objects, properties, operations = [], [], [], []
    for eid, data in cache_data.items():
        entity = {
            "id": eid,
            "name": data.get("name_ru") or eid,
            "statement": data.get("desc_ru") or "",
            "formal_definition": data.get("desc_ru") or "",
            "system": "ZFC",
            "module": "analysis",
            "arity": "?"
        }
        if eid.startswith("axm-"):
            axioms.append(entity)
        elif eid.startswith("obj-"):
            objects.append(entity)
        elif eid.startswith("prop-"):
            properties.append(entity)
        elif eid.startswith("op-") or eid.startswith("oper-"):
            operations.append(entity)
            
    axioms.sort(key=lambda x: x["id"])
    objects.sort(key=lambda x: x["id"])
    properties.sort(key=lambda x: x["id"])
    operations.sort(key=lambda x: x["id"])

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
    
    # Inject natural language description if available
    cache_path = PROJECT_ROOT / "output" / "nl_translations_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if id in cache_data and cache_data[id].get("desc_ru"):
                    entity.statement = cache_data[id]["desc_ru"]
        except Exception:
            pass

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
    
    # Inject natural language description if available
    cache_path = PROJECT_ROOT / "output" / "nl_translations_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if id in cache_data and cache_data[id].get("desc_ru"):
                    entity.formal_definition = cache_data[id]["desc_ru"]
        except Exception:
            pass

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

    # Inject natural language description if available
    cache_path = PROJECT_ROOT / "output" / "nl_translations_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if id in cache_data and cache_data[id].get("desc_ru"):
                    entity.formal_definition = cache_data[id]["desc_ru"]
        except Exception:
            pass

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

    # Inject natural language description if available
    cache_path = PROJECT_ROOT / "output" / "nl_translations_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if id in cache_data and cache_data[id].get("desc_ru"):
                    entity.formal_definition = cache_data[id]["desc_ru"]
        except Exception:
            pass

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
    global api_config
    state.is_compiling = True
    state.cancel_requested = False
    state.mode = mode
    state.logs = []
    
    if mode == "id":
        state.root_entity = value
        cmd = [sys.executable, "-u", str(PROJECT_ROOT / "pipeline" / "generate_answer.py"), "--root", value]
    else:
        state.query = value
        cmd = [sys.executable, "-u", str(PROJECT_ROOT / "pipeline" / "ollama_wrapper.py"), value]
        
    if api_config:
        providers = api_config.get("providers", {})
        models = api_config.get("models", {})
        keys = api_config.get("api_keys", {})
        
        # 1. Extract config
        ext_prov = providers.get("extract")
        ext_model = models.get("extract")
        ext_key = keys.get(ext_prov) if ext_prov else None
        if ext_prov:
            cmd.extend(["--extract-provider", ext_prov])
        if ext_model:
            cmd.extend(["--extract-model", ext_model])
        if ext_key:
            cmd.extend(["--extract-api-key", ext_key])
            
        # 2. Preview config
        prev_prov = providers.get("preview")
        prev_model = models.get("preview")
        prev_key = keys.get(prev_prov) if prev_prov else None
        if prev_prov:
            cmd.extend(["--extract-preview-provider", prev_prov])
        if prev_model:
            cmd.extend(["--extract-preview-model", prev_model])
        if prev_key:
            cmd.extend(["--extract-preview-api-key", prev_key])
            
        # 3. Synth config
        synth_prov = providers.get("synth")
        synth_model = models.get("synth")
        synth_key = keys.get(synth_prov) if synth_prov else None
        if synth_prov:
            cmd.extend(["--synth-provider", synth_prov])
        if synth_model:
            cmd.extend(["--synth-model", synth_model])
        if synth_key:
            cmd.extend(["--synth-api-key", synth_key])
            
        # 4. Lean config
        lean_prov = providers.get("lean")
        lean_model = models.get("lean")
        lean_key = keys.get(lean_prov) if lean_prov else None
        if lean_prov:
            cmd.extend(["--lean-provider", lean_prov])
        if lean_model:
            cmd.extend(["--lean-model", lean_model])
        if lean_key:
            cmd.extend(["--lean-api-key", lean_key])
        
    # Broadcast that compilation has started to all connected sessions
    await manager.broadcast({
        "type": "start",
        "mode": mode,
        "value": value
    })
    
    loop = asyncio.get_running_loop()
    
    def log_and_broadcast(line: str):
        if not line:
            return
        state.logs.append(line)
        asyncio.create_task(manager.broadcast({
            "type": "log",
            "line": line
        }))
        
    run_result = {"returncode": None}

    def run_cmd():
        process = None
        try:
            creationflags = 0
            popen_kwargs = {}
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
                
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                bufsize=1,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                creationflags=creationflags,
                **popen_kwargs
            )
            set_current_compilation_process(process)
            
            for line in iter(process.stdout.readline, ''):
                clean_line = line.rstrip('\r\n')
                loop.call_soon_threadsafe(log_and_broadcast, clean_line)
                
            run_result["returncode"] = process.wait()
        except Exception as e:
            err_msg = f"[System Error] Compilation process failed: {str(e)}"
            loop.call_soon_threadsafe(log_and_broadcast, err_msg)
        finally:
            if process:
                clear_current_compilation_process(process)

    await asyncio.to_thread(run_cmd)
        
    state.is_compiling = False
    was_cancelled = state.cancel_requested
    state.cancel_requested = False
    # Send compilation complete signal to all clients
    if was_cancelled:
        await manager.broadcast({
            "type": "cancelled"
        })
    else:
        await manager.broadcast({
            "type": "done",
            "returncode": run_result["returncode"]
        })


@app.get("/compiler")
async def compiler_page_redirect():
    return RedirectResponse(url="/")


@app.get("/result.pdf")
async def get_result_pdf():
    pdf_path = PROJECT_ROOT / "output" / "result.pdf"
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")
    else:
        raise HTTPException(status_code=404, detail="result.pdf not found")


@app.get("/master.pdf")
async def get_master_pdf():
    # master.pdf устарел, перенаправляем или отдаем full_book.pdf (или ищем в output)
    pdf_path = PROJECT_ROOT / "output" / "master.pdf"
    if not pdf_path.exists():
        pdf_path = PROJECT_ROOT / "output" / "full_book.pdf"
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")
    else:
        raise HTTPException(status_code=404, detail="master.pdf not found")

@app.get("/full_book.pdf")
async def get_full_book_pdf():
    pdf_path = PROJECT_ROOT / "output" / "full_book.pdf"
    if pdf_path.exists():
        return FileResponse(pdf_path, media_type="application/pdf")
    else:
        raise HTTPException(status_code=404, detail="full_book.pdf not found")


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

            elif data["type"] == "cancel":
                # User clicked "Cancel" -> terminate the active pipeline process tree
                if cancel_running_compilation():
                    await manager.broadcast({
                        "type": "cancelling"
                    })
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket)

