import os
BOT_HANDLE = os.getenv("BOT_HANDLE", "")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "")
BOT_DID = os.getenv("BOT_DID", "")
OWNER_DID = os.getenv("OWNER_DID", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PAT = os.getenv("PAT", "")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "qwen2.5-coder-14b-instruct-q5_k_m.gguf")
MODEL_N_CTX = 14080
MODEL_N_THREADS = 4
SEARCH_TIMEOUT = 30
REQUEST_TIMEOUT = 15
ENGLISH_ONLY_SEARCH = True
ENGLISH_ASCII_RATIO = 0.8
ALLOWED_LINK_DOMAINS = ["bsky.app", "atproto.com", "chainbase.com", "tavily.com"]
MAX_LINK_CONTENT_SIZE = 3000
MAX_SEARCH_RESULTS = 3
TOKEN_TO_CHAR_RATIO = 1.0
SIGNATURE_ICONS = "💜💛"
TREND_STATS_EMOJI = "📊"
TREND_EMOJIS = {"new": "🆕", "up": "↗️", "down": "↙️", "same": "➡️"}
TREND_SCORE_SEPARATOR = "⛓️"
TREND_TROPHY = "🏆"
TICKER_LINK_EMOJI = "🔗"
MAX_COMMENT_CHARS = 300
DIGEST_THRESHOLD_HOURS = 2
DIGEST_DESC_MAX_TOKENS = 55
DIGEST_DESC_MAX_CHARS = 235
LLM_TEMP_CASUAL = 0.7
LLM_TEMP_STANDARD = 0.5
LLM_TOKENS_REPLY = 220
LLM_TOKENS_INTENT = 5
LLM_TOKENS_KEYWORD = 10
LLM_TOKENS_REGEN = 15
RAW_DEBUG = os.getenv("DEBUG_OWNER", "false").lower() == "true"
LOG_PROMPTS = os.getenv("LOG_PROMPTS", "false").lower() == "true"
DIGEST_IMAGE_ENABLED = os.getenv("DIGEST_IMAGE", "true").lower() == "true"
IMAGE_ASPECT_RATIO = os.getenv("IMAGE_ASPECT_RATIO", "1024x1024")
