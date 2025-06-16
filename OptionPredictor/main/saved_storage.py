# saved_storage.py
from __future__ import annotations
import json, os, pathlib
from typing import List
import json, pathlib
from typing import Dict, Any


STORAGE_PATH = pathlib.Path.home() / ".idea_suite_saved.json"
NOTES_PATH = pathlib.Path.home() / ".idea_suite_notes.json"

def load_saved_ids() -> List[str]:
    if STORAGE_PATH.is_file():
        try:
            with open(STORAGE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_ids(ids: List[str]) -> None:
    # make sure the directory exists
    try:
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # now write
    try:
        with open(STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(ids, f)
    except Exception as e:
        print(f"Error saving saved-ideas file: {e}")

def load_saved_notes() -> Dict[str, Dict[str, Any]]:
    if NOTES_PATH.is_file():
        try:
            with open(NOTES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_notes(notes_map: Dict[str, Dict[str, Any]]) -> None:
    try:
        NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES_PATH, "w", encoding="utf-8") as f:
            json.dump(notes_map, f, indent=2)
    except Exception as e:
        print(f"Error saving notes file: {e}")
