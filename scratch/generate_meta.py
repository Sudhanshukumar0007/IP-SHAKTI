import os
import json

CORPUS_DIR = r"c:\Users\vom69\Desktop\IP-SHAKTI\Corpus"

def get_source_type_guess(act_name: str) -> str:
    if "pharmacopoeia" in act_name.lower():
        return "pharmacopoeial_standard"
    if "treaty" in act_name.lower() or "protocol" in act_name.lower() or "agreement" in act_name.lower() or "act-1999" in act_name.lower():
        return "treaty"
    if "rule" in act_name.lower():
        return "rule"
    return "statute"

def generate_meta_jsons():
    for jurisdiction in ["national", "international"]:
        jurisdiction_dir = os.path.join(CORPUS_DIR, jurisdiction)
        if not os.path.exists(jurisdiction_dir):
            continue
            
        for act_name in os.listdir(jurisdiction_dir):
            act_dir = os.path.join(jurisdiction_dir, act_name)
            if not os.path.isdir(act_dir):
                continue
                
            meta_path = os.path.join(act_dir, "meta.json")
            if not os.path.exists(meta_path):
                # We can also store act_name here to be explicit
                meta_data = {
                    "act_name": act_name.replace('-', ' ').title(),
                    "source_type": get_source_type_guess(act_name)
                }
                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump(meta_data, f, indent=4)
                print(f"Created {meta_path}")

if __name__ == "__main__":
    generate_meta_jsons()
