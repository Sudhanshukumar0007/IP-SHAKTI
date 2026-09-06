import os
import asyncio
from dotenv import load_dotenv
load_dotenv()
from graph.graph import graph

query = """I am an AYUSH startup. We have developed a shelf-stable oral liquid formulation. It contains a standard aqueous extract of Withania somnifera (Ashwagandha) prepared strictly according to the Bhaishajya Ratnavali. However, we have added a novel, synergistic combination of two specific isolated fractions from Piper nigrum (Black Pepper) and Zingiber officinale (Ginger) that are not mentioned in any First-Schedule authoritative text. This combination enhances the bioavailability of the Ashwagandha by 40%, which we have demonstrated through in-vitro data. We want to commercialize this in India and export it to the US and Europe. Classification: How is this formulation classified under the Drugs and Cosmetics Act/Rules, and does it qualify as a 'Phytopharmaceutical drug' or an 'Ayurveda Aahar'? India IP & ABS: Can we patent this formulation in India, or does it face a Section 3(p) or Section 3(e) bar under the Patents Act? What specific compliance forms and approvals do we need from the NBA before applying for the patent and before commercialization? International: Does the inclusion of Ashwagandha trigger WIPO GRATK or TKDL disclosures if we file a PCT? Are there specific benefit-sharing obligations if we license the IP in Europe?"""

state = {
    'session_id': 'debug-123',
    'raw_query': query,
    'jurisdiction_mode': 'both',
    'language': 'en',
    'formulation_category': 'ayurveda_aahar' # mock classifier result
}

print("Invoking graph...")
result = graph.invoke(state)

print("\n=== EXECUTION TRACE ===")
for trace in result.get('execution_trace', []):
    print(trace)

print("\n=== TASK RESULTS ===")
for tr in result.get('task_results', []):
    print(f"Task: {tr['task_id']}")
    print(f"Question: {tr['question']}")
    print(f"Max Sim: {tr['max_similarity']}, Mean Sim: {tr['mean_similarity']}")
    print(f"Sufficient: {tr['sufficient']}, Reason: {tr['abstain_reason']}")
    print("---")
