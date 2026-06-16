import os
import time
import threading
from google import genai
from config import DEFAULT_KEY_COOLDOWN_SECONDS, SAFETY_RETRY_SECONDS

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

class GeminiKeyManager:
    def __init__(self):
        self.clients = []
        self.raw_keys = {} # Store raw keys to allow client regeneration
        self.lock = threading.Lock()
        self.current_index = 0
        
        # ─── Bulletproof Native .env Loader ───
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if load_dotenv:
            load_dotenv(env_path)
        elif os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip('"\'')
        
        for key, value in os.environ.items():
            if key.startswith("GEMINI_API_KEY") and value.strip():
                clean_key = value.strip()
                self.raw_keys[key] = clean_key
                self.clients.append({
                    "client": genai.Client(api_key=clean_key),
                    "key_id": key,
                    "next_available_time": 0.0  
                })
        
        if not self.clients:
            raise ValueError(f"❌ CRITICAL: No GEMINI_API_KEY found! Looked in: {env_path}")
        
        print(f"🔐 KeyManager Initialized: Armed with {len(self.clients)} API keys.")

    def get_available_client(self):
        while True:
            with self.lock:
                current_time = time.time()
                client_count = len(self.clients)

                for offset in range(client_count):
                    idx = (self.current_index + offset) % client_count
                    candidate = self.clients[idx]

                    if current_time >= candidate["next_available_time"]:
                        self.current_index = (idx + 1) % client_count
                        return candidate["client"], candidate["key_id"]

                next_available_time = min(c["next_available_time"] for c in self.clients)
                sleep_time = next_available_time - current_time

            print(f"⏳ All keys maxed out. Sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)

    def report_exhaustion(self, key_id, cooldown_seconds=DEFAULT_KEY_COOLDOWN_SECONDS):
        with self.lock:
            for c in self.clients:
                if c["key_id"] == key_id:
                    if c["next_available_time"] < time.time() + cooldown_seconds:
                        c["next_available_time"] = time.time() + cooldown_seconds
                        print(f"⚠️ {key_id} quota exhausted. Placing in timeout for {cooldown_seconds}s.")
                    break

    def regenerate_client(self, key_id):
        """
        Destroys the current genai.Client and builds a fresh one.
        This severs the HTTP keep-alive connection pool, forcing Google's
        safety classifiers to evaluate the next request from a clean slate.
        """
        with self.lock:
            for c in self.clients:
                if c["key_id"] == key_id:
                    print(f"🔥 Connection tainted. Burning and regenerating client for {key_id}...")
                    c["client"] = genai.Client(api_key=self.raw_keys[key_id])
                    c["next_available_time"] = time.time() + SAFETY_RETRY_SECONDS # Brief pause to let the network clear
                    break
