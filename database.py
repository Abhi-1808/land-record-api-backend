import os
import certifi
from pymongo import MongoClient

MONGODB_URI = os.getenv("MONGODB_URI")

client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
db = client["land_record_db"]
documents_collection = db["documents"]
verification_logs_collection = db["verification_logs"]