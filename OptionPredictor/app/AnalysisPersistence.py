import json
from pathlib import Path
from datetime import datetime
import uuid
import numpy as np

class NumpyJSONEncoder(json.JSONEncoder):
    """
    A custom JSON encoder that handles NumPy data types for foolproof serialization.
    """
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        # Let the base class default method raise the TypeError for other types
        return super().default(obj)

class AnalysisPersistence:
    """Handles saving and loading analysis states to a JSON file."""
    def __init__(self, filepath: Path = None):
        if filepath is None:
            self.filepath = Path.home() / ".option_analyzer_analyses.json"
        else:
            self.filepath = filepath
        
        self.analyses = self._load_from_disk()

    def _load_from_disk(self):
        """Loads all saved analyses from the JSON file."""
        if not self.filepath.exists():
            return {}
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_to_disk(self):
        """
        Saves the current dictionary of analyses to the file, using the
        custom encoder to handle special data types.
        """
        try:
            with open(self.filepath, 'w') as f:
                # **FIX**: Use the custom NumpyJSONEncoder during the save process
                json.dump(self.analyses, f, indent=4, cls=NumpyJSONEncoder)
        except IOError as e:
            print(f"Error saving analyses: {e}")
        except TypeError as e:
            print(f"Error serializing data to JSON: {e}")

    def get_all_analyses(self):
        """Returns a list of all analyses, sorted by most recent first."""
        return sorted(self.analyses.values(), key=lambda x: x['metadata']['timestamp'], reverse=True)

    def save_analysis(self, name: str, notes: str, analysis_data: dict):
        """Saves a new analysis session."""
        analysis_id = str(uuid.uuid4())
        
        # No need to manually convert data here anymore, the encoder handles it
        self.analyses[analysis_id] = {
            'id': analysis_id,
            'metadata': {
                'name': name,
                'notes': notes,
                'timestamp': datetime.now().isoformat()
            },
            'analysis_data': analysis_data # Store the original data
        }
        self._save_to_disk()
        return analysis_id
    
    def update_analysis_notes(self, analysis_id: str, new_notes: str):
        """Updates the notes for a specific saved analysis."""
        if analysis_id in self.analyses:
            self.analyses[analysis_id]['metadata']['notes'] = new_notes
            self._save_to_disk()
            return True
        return False

    def delete_analysis(self, analysis_id: str):
        """Deletes an analysis by its ID."""
        if analysis_id in self.analyses:
            del self.analyses[analysis_id]
            self._save_to_disk()
            return True
        return False