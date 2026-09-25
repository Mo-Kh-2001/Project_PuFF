import hashlib

def hasher(file_path):
    hashed = hashlib.sha256()
    with open(file_path,"rb") as o:
        
        chunk_size = 8192
        while True:
            chunk = o.read(chunk_size)
            if not chunk:
                break
            hashed.update(chunk)
        
    return hashed.hexdigest()
    

