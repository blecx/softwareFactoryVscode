#!/usr/bin/env python3
import sys
import subprocess
print("Finding next issue...")
args = ["python", "-m", "factory_runtime.agents.maestro_cli", "next-issue"] + sys.argv[1:]
subprocess.run(args)
