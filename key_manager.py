import os
import threading
import time

from google import genai

from config import DEFAULT_KEY_COOLDOWN_SECONDS, SAFETY_RETRY_SECONDS

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


class GeminiKeyManager:
    """Round-robin manager for one explicitly named Gemini API key pool."""

    def __init__(
        self,
        *,
        key_prefix: str = "GEMINI_API_KEY",
        required: bool = True,
        pool_name: str = "Gemini text",
    ):
        self.clients = []
        self.raw_keys = {}
        self.lock = threading.Lock()
        self.current_index = 0
        self.key_prefix = key_prefix
        self.pool_name = pool_name
        self._vision_key_manager = None

        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if load_dotenv:
            load_dotenv(env_path)
        elif os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip().strip('"\'')

        for key, value in sorted(os.environ.items()):
            if key.startswith(self.key_prefix) and value.strip():
                clean_key = value.strip()
                self.raw_keys[key] = clean_key
                self.clients.append({
                    "client": genai.Client(api_key=clean_key),
                    "key_id": key,
                    "next_available_time": 0.0,
                })

        if not self.clients and required:
            raise ValueError(f"No {self.key_prefix} found. Looked in: {env_path}")
        if self.clients:
            print(f"KeyManager initialized {self.pool_name} pool with {len(self.clients)} API key(s).")

    @property
    def has_keys(self) -> bool:
        return bool(self.clients)

    def get_vision_key_manager(self):
        """Return the isolated, optional pool used only by Gemini Vision."""
        with self.lock:
            if self._vision_key_manager is None:
                self._vision_key_manager = GeminiVisionKeyManager()
            return self._vision_key_manager

    def get_available_client(self):
        if not self.clients:
            raise RuntimeError(f"No API keys are configured for the {self.pool_name} pool.")
        while True:
            with self.lock:
                current_time = time.time()
                client_count = len(self.clients)

                for offset in range(client_count):
                    index = (self.current_index + offset) % client_count
                    candidate = self.clients[index]
                    if current_time >= candidate["next_available_time"]:
                        self.current_index = (index + 1) % client_count
                        return candidate["client"], candidate["key_id"]

                next_available_time = min(client["next_available_time"] for client in self.clients)
                sleep_time = next_available_time - current_time

            print(f"All {self.pool_name} keys are cooling down for {sleep_time:.2f} seconds.")
            time.sleep(max(0.0, sleep_time))

    def report_exhaustion(self, key_id, cooldown_seconds=DEFAULT_KEY_COOLDOWN_SECONDS):
        with self.lock:
            for client in self.clients:
                if client["key_id"] == key_id:
                    next_available_time = time.time() + cooldown_seconds
                    if client["next_available_time"] < next_available_time:
                        client["next_available_time"] = next_available_time
                        print(f"{key_id} quota exhausted. Cooling down for {cooldown_seconds}s.")
                    break

    def regenerate_client(self, key_id):
        """Rebuild one client after a transient safety-classifier failure."""
        with self.lock:
            for client in self.clients:
                if client["key_id"] == key_id:
                    print(f"Regenerating client for {key_id}.")
                    client["client"] = genai.Client(api_key=self.raw_keys[key_id])
                    client["next_available_time"] = time.time() + SAFETY_RETRY_SECONDS
                    break


class GeminiVisionKeyManager(GeminiKeyManager):
    """Optional round-robin key pool reserved for conditional image fallback.

    Keys must be named ``GEMINI_VISION_API_KEY`` or
    ``GEMINI_VISION_API_KEY_<suffix>``. They are deliberately never shared
    with chapter text extraction.
    """

    def __init__(self):
        super().__init__(
            key_prefix="GEMINI_VISION_API_KEY",
            required=False,
            pool_name="Gemini Vision",
        )
