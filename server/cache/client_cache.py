import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ClientCache:
    """Client cache system for storing chat responses from regular users"""

    def __init__(self, cache_file: str = "client_cache_data.json"):
        self.cache_file = cache_file
        self.cache_data = self._load_cache_data()

    def _load_cache_data(self) -> Dict:
        """Load client cache data from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading client cache: {e}")
        return {}

    def _save_cache_data(self) -> bool:
        """Save client cache data to file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Error saving client cache: {e}")
            return False

    def get_cached_response(self, question: str) -> Optional[Dict]:
        """Get cached response for a question"""
        question_lower = question.lower().strip()
        return self.cache_data.get(question_lower)

    def cache_response(self, question: str, response: str, model: str = "unknown", user_id: str = "anonymous") -> bool:
        """Cache a response for a question"""
        try:
            question_lower = question.lower().strip()

            # Create cache entry
            cache_entry = {
                "question": question,
                "response": response,
                "model": model,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "hit_count": 1,
                "source": "client"
            }

            # If entry exists, increment hit count
            if question_lower in self.cache_data:
                cache_entry["hit_count"] = self.cache_data[question_lower]["hit_count"] + 1

            # Store the entry
            self.cache_data[question_lower] = cache_entry

            # Save to file
            return self._save_cache_data()

        except Exception as e:
            print(f"❌ Error caching response: {e}")
            return False

    def increment_hit_count(self, question: str) -> bool:
        """Increment hit count for a cached response"""
        try:
            question_lower = question.lower().strip()
            if question_lower in self.cache_data:
                self.cache_data[question_lower]["hit_count"] += 1
                return self._save_cache_data()
        except Exception as e:
            print(f"❌ Error incrementing hit count: {e}")
        return False

    def get_all_entries(self) -> List[Dict]:
        """Get all client cache entries"""
        return list(self.cache_data.values())

    def get_cache_stats(self) -> Dict:
        """Get client cache statistics"""
        total_entries = len(self.cache_data)
        total_hits = sum(entry.get("hit_count", 0)
                         for entry in self.cache_data.values())

        # Calculate cache file size
        cache_size = 0
        try:
            if os.path.exists(self.cache_file):
                cache_size = os.path.getsize(self.cache_file)
        except:
            pass

        return {
            "total_entries": total_entries,
            "total_hits": total_hits,
            "cache_file_size": cache_size,
            "cache_file_exists": os.path.exists(self.cache_file)
        }

    def remove_entry(self, question: str) -> bool:
        """Remove a cache entry"""
        try:
            question_lower = question.lower().strip()
            if question_lower in self.cache_data:
                del self.cache_data[question_lower]
                return self._save_cache_data()
        except Exception as e:
            print(f"❌ Error removing cache entry: {e}")
        return False

    def clear_all(self) -> bool:
        """Clear all client cache entries"""
        try:
            self.cache_data = {}
            return self._save_cache_data()
        except Exception as e:
            print(f"❌ Error clearing client cache: {e}")
            return False

    def update_entry(self, question: str, new_response: str) -> bool:
        """Update an existing cache entry"""
        try:
            question_lower = question.lower().strip()
            if question_lower in self.cache_data:
                self.cache_data[question_lower]["response"] = new_response
                self.cache_data[question_lower]["timestamp"] = datetime.now(
                ).isoformat()
                return self._save_cache_data()
        except Exception as e:
            print(f"❌ Error updating cache entry: {e}")
        return False


# Global client cache instance (DISABLED)
# client_cache = ClientCache()
