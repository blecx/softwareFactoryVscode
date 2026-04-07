import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))
import factory_workspace

config = factory_workspace.build_runtime_config(Path.cwd() / ".tmp" / "single-tenant-proof-rerun", factory_dir=Path.cwd() / ".tmp" / "single-tenant-proof-rerun" / ".softwareFactoryVscode")
print("FACTORY_DATA_DIR IN ENV VALUES:", config.env_values.get("FACTORY_DATA_DIR"))

from factory_stack import ensure_data_dirs_ready
ensure_data_dirs_ready(config)
import os
print("DID IT CREATE TARGET DIR?", os.path.exists(config.env_values.get("FACTORY_DATA_DIR")))

config2 = factory_workspace.build_runtime_config(Path.cwd(), factory_dir=Path.cwd())
print("FACTORY_DATA_DIR IN HOST ENV VALUES:", config2.env_values.get("FACTORY_DATA_DIR"))
ensure_data_dirs_ready(config2)
print("DID IT CREATE HOST DIR?", os.path.exists(config2.env_values.get("FACTORY_DATA_DIR")))

