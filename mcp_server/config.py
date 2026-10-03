import os
from pathlib import Path

from dotenv import load_dotenv

# Reads mcp_server/.env (never committed). Real environment variables win over the file.
load_dotenv(Path(__file__).parent / ".env")

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")

# Adzuna needs a country code; "in" = India (same as the original HirePath code).
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "in")
