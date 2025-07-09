import json
import os
from datetime import datetime
from pathlib import Path

class TokenUsageTracker:
    """
    Manages daily API token usage, persisting the count to a local file.
    """
    def __init__(self, daily_limit: int = 500_000):
        self.daily_limit = daily_limit
        self.usage_file = Path.home() / ".option_analyzer_token_usage.json"
        self.tokens_used = 0
        self.last_reset_date = ""
        self._load_usage()

    def _load_usage(self):
        """Loads usage data and resets it if the date has changed."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.usage_file.exists():
            try:
                data = json.loads(self.usage_file.read_text())
                if data.get("date") == today_str:
                    self.tokens_used = data.get("tokens_used", 0)
                    self.last_reset_date = today_str
                else:
                    # New day, reset the count
                    self._reset_usage(today_str)
            except (json.JSONDecodeError, TypeError):
                self._reset_usage(today_str)
        else:
            self._reset_usage(today_str)
        print(f"[Token Tracker] Initialized. Used today: {self.tokens_used:,}/{self.daily_limit:,}")


    def _save_usage(self):
        """Saves the current token count and date to the file."""
        try:
            data = {"date": self.last_reset_date, "tokens_used": self.tokens_used}
            self.usage_file.write_text(json.dumps(data))
        except IOError as e:
            print(f"Error saving token usage: {e}")

    def _reset_usage(self, today_str: str):
        """Resets the token count for a new day."""
        self.tokens_used = 0
        self.last_reset_date = today_str
        self._save_usage()

    def update_usage(self, response):
        """
        Updates the token count based on a successful Gemini API response.
        'response' is the object returned by gemini's generate_content().
        """
        try:
            # Check if it's a new day before updating
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str != self.last_reset_date:
                self._reset_usage(today_str)

            count = response.usage_metadata.total_token_count
            self.tokens_used += count
            self._save_usage()
            print(f"[Token Tracker] Request used {count} tokens. Total today: {self.tokens_used:,}/{self.daily_limit:,}")
        except Exception as e:
            print(f"Could not update token usage from response: {e}")


    def is_limit_reached(self) -> bool:
        """Checks if the daily token limit has been exceeded."""
        # Also check date here in case the app has been running over midnight
        today_str = datetime.now().strftime("%Y-%m-%d")
        if today_str != self.last_reset_date:
            self._reset_usage(today_str)
            return False
        return self.tokens_used >= self.daily_limit