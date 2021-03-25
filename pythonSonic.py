from dotenv import load_dotenv
import os

load_dotenv()

mongoURI = os.getenv("MONGO_URL")
print(mongoURI)