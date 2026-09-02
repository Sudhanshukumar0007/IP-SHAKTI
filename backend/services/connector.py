import datetime
from typing import List, Dict, Any
from duckduckgo_search import DDGS

class LiveRegistryConnector:
    def __init__(self):
        self.ddgs = DDGS()

    def search_registry(self, query: str) -> Dict[str, Any]:
        """
        Searches for live factual evidence regarding patents and IP.
        """
        # A simpler query that works better with DDGS. We append keywords to target patent registries.
        full_query = f"{query} patent registry India WIPO"
        
        evidence_list = []
        try:
            results = self.ddgs.text(full_query, max_results=3)
            for res in results:
                url = res.get('href', '')
                
                # Determine source name loosely based on URL or title
                if "ipindia" in url:
                    source_name = "IP India"
                elif "wipo" in url:
                    source_name = "WIPO"
                else:
                    source_name = "Web Source"
                
                evidence_list.append({
                    "source": source_name,
                    "retrieved_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "title": res.get('title', 'Unknown Title'),
                    "url": url,
                    "evidence": res.get('body', ''),
                    "record_id": url.split("/")[-1] if "/" in url else "unknown"
                })
            
            status = "success" if evidence_list else "no_results"
        except Exception as e:
            status = f"error: {str(e)}"
            
        return {
            "status": status,
            "evidence": evidence_list
        }

