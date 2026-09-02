import os
import shutil
import re

CORPUS_DIR = r"c:\Users\vom69\Desktop\IP-SHAKTI\Corpus"
NATIONAL_DIR = os.path.join(CORPUS_DIR, "national")
INTERNATIONAL_DIR = os.path.join(CORPUS_DIR, "international")

def to_kebab_case(s):
    s = s.replace('.pdf', '')
    # Replace underscores with hyphens before removing special characters
    s = s.replace('_', '-')
    s = re.sub(r'[^a-zA-Z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s)
    s = s.lower().strip('-')
    return s

def organize_national():
    # Regular expressions for matching patterns
    date_regex = re.compile(r'(\d{4})-(\d{2})(?:-\d{2})?')
    year_regex = re.compile(r'(\d{4})')
    
    for filename in os.listdir(NATIONAL_DIR):
        file_path = os.path.join(NATIONAL_DIR, filename)
        if not os.path.isfile(file_path) or not filename.endswith('.pdf'):
            continue
            
        # Example: the_biological_diversity_act_2002_2003-02-05.pdf
        act_name_raw = filename.split('_2')[0] if '_2' in filename else filename.split('.')[0]
        act_name_raw = act_name_raw.replace('the_', '')
        act_dir_name = to_kebab_case(act_name_raw)
        
        act_dir_path = os.path.join(NATIONAL_DIR, act_dir_name)
        os.makedirs(act_dir_path, exist_ok=True)
        
        # Determine base vs consolidated and year
        doc_type = "base"
        year = "unknown"
        year_match = None
        
        # Check if it has a specific date like 2026-05-05
        date_match = date_regex.search(filename)
        if date_match:
            year_val = date_match.group(1)
            month_val = date_match.group(2)
            year = f"{year_val}_{month_val}"
            # usually if there's a specific later date, it's consolidated or base of that date
            if year_val > "2010" and ("2000" in filename or "19" in filename): # loosely if act is older than the date
                doc_type = "consolidated"
        else:
            year_match = year_regex.search(filename)
            if year_match:
                year = year_match.group(1)
        
        # some hardcoded doc_type if we know the act
        if date_match and (date_match.group(1) != year_match.group(1) if year_match else True):
            doc_type = "consolidated"
            
        # Exception for acts where we just want base
        if "2006-08-23" in filename or "2001-10-30" in filename:
            doc_type = "base"

        new_filename = f"{doc_type}_{year}_en.pdf"
        new_file_path = os.path.join(act_dir_path, new_filename)
        shutil.move(file_path, new_file_path)
        print(f"Moved {filename} -> {act_dir_name}/{new_filename}")

def organize_international():
    for filename in os.listdir(INTERNATIONAL_DIR):
        file_path = os.path.join(INTERNATIONAL_DIR, filename)
        if not os.path.isfile(file_path) or not filename.endswith('.pdf'):
            continue
            
        act_name_raw = filename.replace('.pdf', '')
        act_dir_name = to_kebab_case(act_name_raw)
        
        act_dir_path = os.path.join(INTERNATIONAL_DIR, act_dir_name)
        os.makedirs(act_dir_path, exist_ok=True)
        
        # Try to extract a year
        year_match = re.search(r'(\d{4})(?:_(\d{2}))?', filename)
        year = "unknown"
        if year_match:
            year = year_match.group(1)
            if year_match.group(2):
                year += f"_{year_match.group(2)}"
        else:
            # Look for specific treaties to hardcode year
            if "wipo" in filename.lower(): year = "2024"
            if "budapest" in filename.lower(): year = "1977"
            if "madrid" in filename.lower(): year = "1989"
            if "nagoya" in filename.lower(): year = "2010"
            
        new_filename = f"base_{year}_en.pdf"
        new_file_path = os.path.join(act_dir_path, new_filename)
        shutil.move(file_path, new_file_path)
        print(f"Moved {filename} -> {act_dir_name}/{new_filename}")
        
def organize_ayurvedic():
    # Handle Ayurvedic Pharmacopoeia folders
    for part in ["Ayurvedic Pharmacopoeia of India Part 1", "Ayurvedic Pharmacopoeia of India Part 2"]:
        src_dir = os.path.join(NATIONAL_DIR, part)
        if not os.path.exists(src_dir):
            continue
            
        act_dir_name = to_kebab_case(part)
        act_dir_path = os.path.join(NATIONAL_DIR, act_dir_name)
        os.makedirs(act_dir_path, exist_ok=True)
        
        for filename in os.listdir(src_dir):
            if not filename.endswith('.pdf'): continue
            file_path = os.path.join(src_dir, filename)
            
            # Vol_1_1986.pdf -> base_1986_en.pdf (but maybe with vol)
            # Let's use volume as part of document_type, e.g., vol1_1986_en.pdf
            # Actually schema says base, amendment, consolidated.
            # We can use base-vol1
            vol_match = re.search(r'Vol_(\d+)_(\d{4})', filename)
            if vol_match:
                vol = vol_match.group(1)
                year = vol_match.group(2)
                new_filename = f"base-vol{vol}_{year}_en.pdf"
                shutil.move(file_path, os.path.join(act_dir_path, new_filename))
                print(f"Moved {part}/{filename} -> {act_dir_name}/{new_filename}")
        
        # Remove empty dir
        if not os.listdir(src_dir):
            os.rmdir(src_dir)

if __name__ == "__main__":
    organize_national()
    organize_ayurvedic()
    organize_international()
    print("Corpus structured successfully!")
