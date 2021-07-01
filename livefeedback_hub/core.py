import hashlib

def get_user_hash(user_model) -> str:
    m = hashlib.sha256()
    name = user_model["name"].encode("utf-8")
    m.update(name)
    return m.hexdigest()