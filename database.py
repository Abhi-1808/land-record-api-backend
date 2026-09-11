import os
from types import SimpleNamespace
from uuid import uuid4

import certifi
from pymongo import MongoClient

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


if MONGODB_URI and "your_mongodb_connection_string" not in MONGODB_URI:
	client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
	db = client["land_record_db"]
	documents_collection = db["documents"]
	verification_logs_collection = db["verification_logs"]
else:
	documents_collection = InMemoryCollection()
	verification_logs_collection = InMemoryCollection()