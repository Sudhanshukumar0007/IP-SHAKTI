import os
import json
import hashlib
from datetime import datetime

# Helper to calculate file hash
def get_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as file:
        while chunk := file.read(8192):
            h.update(chunk)
    return h.hexdigest()

def patch_registry():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    corpus_dir = os.path.join(project_root, "Corpus")
    registry_path = os.path.join(backend_dir, "registry.json")
    
    with open(registry_path, 'r', encoding='utf-8') as f:
        registry = json.load(f)
        
    today = datetime.now().strftime("%Y-%m-%d")
    added = 0
    
    for jurisdiction in os.listdir(corpus_dir):
        jur_dir = os.path.join(corpus_dir, jurisdiction)
        if not os.path.isdir(jur_dir):
            continue
            
        for act_folder in os.listdir(jur_dir):
            act_dir = os.path.join(jur_dir, act_folder)
            if not os.path.isdir(act_dir):
                continue
                
            display_act_name = act_folder.replace('-', ' ').title()
            
            # Check meta.json
            meta_path = os.path.join(act_dir, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        display_act_name = meta.get('act_name', display_act_name)
                except Exception:
                    pass
            
            for filename in os.listdir(act_dir):
                if not filename.endswith('.pdf'):
                    continue
                    
                parts = filename.replace('.pdf', '').split('_')
                if len(parts) >= 3:
                    version = "_".join(parts[1:-1])
                    language = parts[-1]
                elif len(parts) == 2:
                    version = "unknown"
                    language = parts[-1]
                else:
                    version = "unknown"
                    language = "en"
                    
                document_id = hashlib.sha256(
                    f"{jurisdiction}_{act_folder}_{filename}_{version}".encode()
                ).hexdigest()
                
                if document_id not in registry:
                    file_path = os.path.join(act_dir, filename)
                    pdf_hash = get_file_hash(file_path)
                    source_pdf_path = os.path.join("Corpus", jurisdiction, act_folder, filename).replace('\\', '/')
                    
                    registry[document_id] = {
                        "act_name": display_act_name,
                        "jurisdiction": jurisdiction,
                        "source_pdf_path": source_pdf_path,
                        "version": version,
                        "language": language,
                        "pdf_hash": pdf_hash,
                        "ingested_date": today,
                    }
                    added += 1
                    print(f"Added to registry: {document_id} -> {source_pdf_path}")
                    
    if added > 0:
        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(registry, f, indent=4)
        print(f"Patched {added} entries in registry.json")
    else:
        print("Registry is up to date.")

if __name__ == "__main__":
    patch_registry()
