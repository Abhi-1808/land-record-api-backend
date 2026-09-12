import os
from types import SimpleNamespace
from uuid import uuid4
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")


class InMemoryCollection:
    def __init__(self):
        self._documents = []

    def insert_one(self, document):
        stored = {"_id": uuid4(), **document}
        self._documents.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    def find_one(self, query):
        return next(
            (document for document in self._documents if all(document.get(key) == value for key, value in query.items())),
            None,
        )

    def update_one(self, query, update):
        document = self.find_one(query)
        if document:
            document.update(update.get("$set", {}))

    def find(self, query=None):
        query = query or {}
        return [
            document for document in self._documents
            if all(document.get(key) == value for key, value in query.items())
        ]

    def all(self):
        return list(self._documents)


# Initialize MongoDB Client
if MONGODB_URI and "your_mongodb_connection_string" not in MONGODB_URI:
    try:
        # If using MongoDB Atlas cloud connection
        if "mongodb+srv" in MONGODB_URI:
            import certifi
            client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
        else:
            # Local MongoDB instance (no TLS requirement)
            client = MongoClient(MONGODB_URI)
            
        db = client["land_record_db"]
        documents_collection = db["documents"]
        verification_logs_collection = db["verification_logs"]
        case_collection = db["verification_cases"]
        credential_collection = db["verifiable_credentials"]
        print("[Database] Connected successfully to MongoDB ('land_record_db')")
    except Exception as e:
        print(f"[Database Warning] MongoDB connection error: {e}. Falling back to in-memory.")
        documents_collection = InMemoryCollection()
        verification_logs_collection = InMemoryCollection()
        case_collection = InMemoryCollection()
        credential_collection = InMemoryCollection()
else:
    print("[Database] Using InMemoryCollection (no active MONGODB_URI)")
    documents_collection = InMemoryCollection()
    verification_logs_collection = InMemoryCollection()
    case_collection = InMemoryCollection()
    credential_collection = InMemoryCollection()