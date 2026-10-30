"""
Plugin Architecture: third-party or site-specific extensions register a new
BaseAgent subclass (or a new ModelBackend) via a small manifest + entry
point, without touching core agents/specialists.py. Plugins live under
/data/plugins/<plugin_name>/ (mounted volume, so operators can drop in a
directory without rebuilding the image) and are loaded dynamically at
startup and on-demand via the API.

Manifest format (plugin.json in the plugin's root):
{
  "name": "vendor-drawing-parser",
  "version": "1.0.0",
  "entry_point": "plugin:VendorDrawingAgent",
  "agent_name": "vendor_drawing"
}
`entry_point` is "<module>:<ClassName>" relative to the plugin directory.
"""
from __future__ import annotations
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from ..db.models import PluginRecord
from ..agents.base import BaseAgent

try:
    from sovereignai_sdk import PluginAgent  # optional — SDK may not be installed in every environment
except ImportError:
    PluginAgent = None  # type: ignore

PLUGIN_DIR = Path("/data/plugins")
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

_loaded_agents: dict[str, BaseAgent] = {}


class PluginLoadError(Exception):
    pass


def _load_manifest(plugin_path: Path) -> dict:
    manifest_path = plugin_path / "plugin.json"
    if not manifest_path.exists():
        raise PluginLoadError(f"Missing plugin.json in {plugin_path}")
    return json.loads(manifest_path.read_text())


def _import_entry_point(plugin_path: Path, entry_point: str):
    module_name, class_name = entry_point.split(":")
    module_file = plugin_path / f"{module_name}.py"
    if not module_file.exists():
        raise PluginLoadError(f"Entry point module not found: {module_file}")

    spec = importlib.util.spec_from_file_location(f"sovereignai_plugin_{plugin_path.name}", module_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore

    cls = getattr(module, class_name, None)
    if cls is None:
        raise PluginLoadError(f"Class {class_name} not found in {module_file}")
    valid_bases = tuple(b for b in (BaseAgent, PluginAgent) if b is not None)
    if not issubclass(cls, valid_bases):
        raise PluginLoadError(f"{class_name} must subclass BaseAgent or sovereignai_sdk.PluginAgent")
    return cls


def discover_plugins() -> list[dict]:
    manifests = []
    for entry in PLUGIN_DIR.iterdir():
        if entry.is_dir():
            try:
                manifests.append({**_load_manifest(entry), "path": str(entry)})
            except PluginLoadError as exc:
                manifests.append({"name": entry.name, "error": str(exc), "path": str(entry)})
    return manifests


def load_plugin(db: Session, plugin_name: str, installed_by: str) -> dict:
    plugin_path = PLUGIN_DIR / plugin_name
    if not plugin_path.exists():
        raise PluginLoadError(f"No plugin directory found at {plugin_path}")

    manifest = _load_manifest(plugin_path)
    agent_cls = _import_entry_point(plugin_path, manifest["entry_point"])
    agent_instance = agent_cls()
    _loaded_agents[manifest["agent_name"]] = agent_instance

    record = db.query(PluginRecord).filter(PluginRecord.name == manifest["name"]).first()
    if record:
        record.version = manifest.get("version", "0.0.0")
        record.entry_point = manifest["entry_point"]
        record.enabled = "true"
        record.manifest = manifest
    else:
        record = PluginRecord(
            id=str(uuid.uuid4()), name=manifest["name"], version=manifest.get("version", "0.0.0"),
            entry_point=manifest["entry_point"], enabled="true", manifest=manifest,
        )
        db.add(record)
    db.commit()
    db.refresh(record)

    return {"name": record.name, "version": record.version, "agent_name": manifest["agent_name"],
            "status": "loaded"}


def get_loaded_agents() -> dict[str, BaseAgent]:
    """Merged into the core agent registry at Orchestrator construction time
    (see agents/specialists.py build_agent_registry() callers) so plugin
    agents participate in the same TaskGraph execution as built-in ones."""
    return dict(_loaded_agents)


def list_installed(db: Session) -> list[dict]:
    rows = db.query(PluginRecord).order_by(PluginRecord.installed_at.desc()).all()
    return [
        {"id": r.id, "name": r.name, "version": r.version, "entry_point": r.entry_point,
         "enabled": r.enabled == "true", "installed_at": r.installed_at.isoformat() if r.installed_at else None}
        for r in rows
    ]


def disable_plugin(db: Session, name: str) -> dict:
    record = db.query(PluginRecord).filter(PluginRecord.name == name).first()
    if not record:
        raise KeyError("Plugin not found")
    record.enabled = "false"
    db.commit()
    manifest = record.manifest or {}
    _loaded_agents.pop(manifest.get("agent_name", ""), None)
    return {"name": name, "status": "disabled"}
