import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/land_record_db")


class InMemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self.data: List[Dict[str, Any]] = []

    def insert_one(self, doc: Dict[str, Any]):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = str(len(self.data) + 1)
        self.data.append(doc_copy)
        return type("InsertResult", (), {"inserted_id": doc_copy["_id"]})()

    def find_one(self, query: Optional[Dict[str, Any]] = None):
        if not query:
            return self.data[0] if self.data else None
        for item in self.data:
            match = True
            for k, v in query.items():
                if k == "$or" and isinstance(v, list):
                    if not any(all(item.get(ok) == ov for ok, ov in cond.items()) for cond in v):
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                return item
        return None

    def find(self, query: Optional[Dict[str, Any]] = None):
        if not query:
            return list(self.data)
        results = []
        for item in self.data:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                results.append(item)
        return results

    def count_documents(self, filter: Optional[Dict[str, Any]] = None) -> int:
        if not filter:
            return len(self.data)
        return len(self.find(filter))

    def delete_many(self, *args, **kwargs):
        pass

    def create_index(self, *args, **kwargs):
        pass


try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
    client.admin.command("ping")
    db = client.get_default_database(default="land_record_db")
    documents_collection = db["documents"]
    verification_logs_collection = db["verification_logs"]
    case_collection = db["cases"]
    credential_collection = db["credentials"]

    # Clean legacy null records to prevent duplicate key errors during index creation
    try:
        documents_collection.delete_many({
            "$or": [
                {"document_hash": None},
                {"parcel_id": None}
            ]
        })
        documents_collection.create_index(
            [("document_hash", 1), ("parcel_id", 1)],
            unique=True,
            name="unique_doc_hash_parcel"
        )
    except Exception:
        pass

    print(f"[Database] Connected successfully to MongoDB ('{db.name}')")

except Exception as e:
    print(f"[Database Warning] MongoDB unavailable ({e}). Using In-Memory Storage.")
    documents_collection = InMemoryCollection("documents")
    verification_logs_collection = InMemoryCollection("verification_logs")
    case_collection = InMemoryCollection("cases")
    credential_collection = InMemoryCollection("credentials")