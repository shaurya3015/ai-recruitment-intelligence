import json
from pathlib import Path

def fix_metadata():
    storage_path = Path('./qdrant_storage')
    if not storage_path.exists():
        print("No qdrant_storage found.")
        return
        
    for meta_file in storage_path.rglob('*.json'):
        if meta_file.name != "meta.json": continue
        print(f"Fixing {meta_file}...")
        try:
            with open(meta_file, 'r') as f:
                data = json.load(f)
            
            if 'metadata' in data:
                del data['metadata']
                with open(meta_file, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"  -> Removed 'metadata' from {meta_file}")
            else:
                print(f"  -> No 'metadata' found in {meta_file}")
        except Exception as e:
            print(f"  -> Error fixing {meta_file}: {e}")

if __name__ == "__main__":
    fix_metadata()
