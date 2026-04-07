import subprocess
cmd = [
    "docker", "compose", 
    "--project-directory", "/home/sw/work/softwareFactoryVscode/.tmp/single-tenant-proof-rerun/.softwareFactoryVscode", 
    "--env-file", "/home/sw/work/softwareFactoryVscode/.tmp/single-tenant-proof-rerun/.factory.env", 
    "-f", "/home/sw/work/softwareFactoryVscode/.tmp/single-tenant-proof-rerun/.softwareFactoryVscode/compose/docker-compose.factory.yml", 
    "config"
]
result = subprocess.run(cmd, text=True, capture_output=True)
import re
print("FROM PY:")
for line in result.stdout.splitlines():
   if "device:" in line: print(line)
