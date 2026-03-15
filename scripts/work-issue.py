#!/usr/bin/env python3
import sys
import subprocess
print("Bootstrapping work-issue integration via maestro_cli...")
args = ["python", "-m", "factory_runtime.agents.maestro_cli"] + sys.argv[1:]
subprocess.run(args)
