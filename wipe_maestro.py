import os
import re

directories = ['.']
exclude_dirs = {'.git', '.venv', '.pytest_cache', '__pycache__', '.local-tools'}
exclude_files = {
    'howto-extract-softwareFactory.md', 
    'softwareFactoryVscode.md', 
    'externalDevendenciesSoftwareFactory.md',
    'wipe_maestro.py'
}

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    # Skip files that don't have maestro
    if 'maestro' not in content.lower():
        return

    # Apply case sensitive replacements
    new_content = re.sub(r'maestro_adapter', 'factory_adapter', content)
    new_content = re.sub(r'maestro_cli', 'factory_cli', new_content)
    new_content = re.sub(r'maestro-operator', 'factory-operator', new_content)
    new_content = re.sub(r'docker-compose\.maestro\.yml', 'docker-compose.factory.yml', new_content)

    new_content = re.sub(r'maestro', 'factory', new_content)
    new_content = re.sub(r'Maestro', 'Factory', new_content)
    new_content = re.sub(r'MAESTRO', 'FACTORY', new_content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated: {filepath}")

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for file in files:
        if file in exclude_files:
            continue
        replace_in_file(os.path.join(root, file))
