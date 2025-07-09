import json
from datetime import datetime

class TokenUsageTracker:
    """
    Tracks daily token usage and enforces a limit.
    Usage data is persisted in a JSON file.
    """
    def __init__(self, file_path="token_usage.json", daily_limit=33000):
        self.file_path = file_path
        self.daily_limit = daily_limit
        self.tokens_used = 0
        self.date = datetime.now().strftime("%Y-%m-%d")
        self._load_usage()

    def _load_usage(self):
        """Loads usage from the file or resets it if the date has changed."""
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            
            if data.get("date") == self.date:
                self.tokens_used = data.get("tokens_used", 0)
            else:
                # The date has changed, so reset the counter
                self.tokens_used = 0
                self._save_usage()

        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is empty, start fresh
            self.tokens_used = 0
            self._save_usage()
        
        print(f"[Token Tracker] Initialized. Used today: {self.tokens_used}/{self.daily_limit}")

    def _save_usage(self):
        """Saves the current usage data to the file."""
        with open(self.file_path, 'w') as f:
            json.dump({"date": self.date, "tokens_used": self.tokens_used}, f)

    def update_usage(self, api_response):
        """Updates the token count based on an API response and saves it."""
        try:
            usage_data = api_response.usage_metadata
            total_tokens = usage_data.prompt_token_count + usage_data.candidates_token_count
            self.tokens_used += total_tokens
            self._save_usage()
            print(f"[Token Tracker] Request used {total_tokens} tokens. Total today: {self.tokens_used}/{self.daily_limit}")
        except Exception as e:
            print(f"[Token Tracker] ERROR: Could not update token usage. Reason: {e}")
    
    def is_limit_reached(self) -> bool:
        """Checks if the daily token limit has been reached."""
        return self.tokens_used >= self.daily_limit