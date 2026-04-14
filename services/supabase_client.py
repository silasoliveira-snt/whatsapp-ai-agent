import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)
