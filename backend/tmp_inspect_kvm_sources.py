import json

from cores.dbconnection.mongo import MONGO_URI, get_db


def _normalize(doc):
    out = {}
    for key, value in doc.items():
        if key == "_id":
            out[key] = str(value)
        else:
            out[key] = value
    return out


db = get_db()
print("MONGO_URI", MONGO_URI)
print("DB_NAME", db.name)
print("KVM_SOURCES_COUNT", db.kvm_sources.count_documents({}))
for doc in db.kvm_sources.find().sort("_id", 1).limit(20):
    print(json.dumps(_normalize(doc), default=str, ensure_ascii=False))
