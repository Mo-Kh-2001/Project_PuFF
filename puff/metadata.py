from pathlib import Path

def get_meta_data(path):
    data = path.stat()
    size = data.st_size
    mtime =data.st_mtime
    result = {"size":size,"mtime":mtime}
    return result
if __name__ == "__main__":
    print(get_meta_data(Path("data/2222.jpeg")))
    
