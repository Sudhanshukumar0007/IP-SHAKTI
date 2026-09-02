import os
import shutil

CORPUS_DIR = r"c:\Users\vom69\Desktop\IP-SHAKTI\Corpus"
NATIONAL_DIR = os.path.join(CORPUS_DIR, "national")
INTERNATIONAL_DIR = os.path.join(CORPUS_DIR, "international")

renames = {
    # national
    "biologicaldiversityact": "biological-diversity-act",
    "copyrightact1957": "copyright-act-1957",
    "designact": "design-act",
    "drugsandcosmeticsact1940": "drugs-and-cosmetics-act-1940",
    "drugsandmagicremediesact1954": "drugs-and-magic-remedies-act-1954",
    "foodsafetyandstandardsact": "food-safety-and-standards-act",
    "geographicalindicationsofgoodsact1999": "geographical-indications-of-goods-act-1999",
    "patentsact1970": "patents-act-1970",
    "protectionofplantvarietiesandfarmersrightact": "protection-of-plant-varieties-and-farmers-rights-act",
    "trademarksact1999": "trade-marks-act-1999",

    # international
    "budapesttreaty": "budapest-treaty",
    "conventionofbiologicaldiversity1992": "convention-of-biological-diversity-1992",
    "genevaact19990702": "geneva-act-1999",
    "madridagreementprotocol": "madrid-agreement-protocol",
    "nagoyaprotocolonaccessandbenefitsharing": "nagoya-protocol-on-access-and-benefit-sharing",
    "patentcooperationtreaty1970": "patent-cooperation-treaty-1970",
    "wipotreatyonintellectualpropertygeneticresourcesandassociatedtraditionalknowledge": "wipo-treaty-on-intellectual-property"
}

def move_contents(src, dst):
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        src_path = os.path.join(src, item)
        dst_path = os.path.join(dst, item)
        if os.path.isfile(src_path):
            shutil.move(src_path, dst_path)

def process_renames(base_dir):
    for old_name, new_name in renames.items():
        old_path = os.path.join(base_dir, old_name)
        new_path = os.path.join(base_dir, new_name)
        if os.path.exists(old_path) and os.path.isdir(old_path):
            print(f"Renaming {old_name} -> {new_name}")
            move_contents(old_path, new_path)
            # Remove the old directory if it's empty
            if not os.listdir(old_path):
                os.rmdir(old_path)
            else:
                print(f"Warning: {old_path} is not empty after moving files!")

if __name__ == "__main__":
    process_renames(NATIONAL_DIR)
    process_renames(INTERNATIONAL_DIR)
    print("Folders renamed successfully!")
