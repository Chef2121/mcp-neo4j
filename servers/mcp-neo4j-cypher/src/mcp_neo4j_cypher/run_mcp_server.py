import server
import os
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    server.main(
            db_url=os.getenv("NEO4J_URI"),
            username=os.getenv("NEO4J_USERNAME"),
            password=os.getenv("NEO4J_PASSWORD"),
            database=os.getenv("NEO4J_DATABASE")
        )
    