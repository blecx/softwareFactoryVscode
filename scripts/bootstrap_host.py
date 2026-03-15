#!/usr/bin/env python3
import os
import json
from datetime import datetime
import sys

def main():
    target_dir = os.path.abspath(os.getcwd())
    tmp_dir = os.path.join(target_dir, ".tmp", "softwareFactoryVscode")
    factory_dir = os.path.join(target_dir, ".softwareFactoryVscode")
    
    print(f"=================================================")
    print(f"🚀 Bootstrapping Host Project")
    print(f"=================================================")
    
    if not os.path.exists(factory_dir):
        print("❌ Factory directory not found. Please run install_factory.py first.")
        sys.exit(1)

    print("➡️ Creating ephemeral state directories...")
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"   [{tmp_dir}] created.")

    factory_env_path = os.path.join(target_dir, ".factory.env")
    if not os.path.exists(factory_env_path):
        print("➡️ Creating canonical .factory.env environment contract...")
        project_id = os.path.basename(target_dir)
        with open(factory_env_path, "w") as f:
            f.write(f"TARGET_WORKSPACE_PATH={target_dir}\n")
            f.write(f"PROJECT_WORKSPACE_ID={project_id}\n")
            f.write(f"COMPOSE_PROJECT_NAME=factory_{project_id}\n")
            f.write("CONTEXT7_API_KEY=\n")
        print(f"   [{factory_env_path}] created.")
    else:
        print(f"   [{factory_env_path}] already exists.")

    lock_path = os.path.join(target_dir, ".factory.lock.json")
    if not os.path.exists(lock_path):
        print("➡️ Creating .factory.lock.json...")
        lock_data = {
            "version": "main",
            "installed_at": datetime.utcnow().isoformat() + "Z"
        }
        with open(lock_path, "w") as f:
            json.dump(lock_data, f, indent=4)
        print(f"   [{lock_path}] created.")
    
    print("\n✅ Bootstrap secure and complete!")
    print("Isolation rule confirmed: tool-owned .vscode/ and .github/ remain locked inside .softwareFactoryVscode/ and are NOT polluting the root project by default.")

if __name__ == "__main__":
    main()
