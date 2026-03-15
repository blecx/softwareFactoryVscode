#!/usr/bin/env python3
import os
import sys
import subprocess

def main():
    target_dir = os.path.abspath(os.getcwd())
    factory_dir = os.path.join(target_dir, ".softwareFactoryVscode")

    print(f"=================================================")
    print(f"📦 Installing softwareFactoryVscode")
    print(f"=================================================")
    print(f"Target Project: {target_dir}")
    print(f"Factory Path:   {factory_dir}")
    
    if os.path.exists(factory_dir):
        print("⚠️ Factory is already installed at this path.")
        print("To reinstall, remove the .softwareFactoryVscode directory manually.")
        sys.exit(1)

    repo_url = "https://github.com/blecx/softwareFactoryVscode.git"
    print(f"➡️ Cloning factory repository from {repo_url}...")
    
    try:
        subprocess.run(["git", "clone", repo_url, factory_dir], check=True)
    except subprocess.CalledProcessError:
        print("❌ Installation failed during clone.")
        sys.exit(1)

    print("✅ Factory installed successfully.")
    print("Next step: Run python3 .softwareFactoryVscode/scripts/bootstrap_host.py")

if __name__ == "__main__":
    main()
