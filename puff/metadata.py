from pathlib import Path
from PIL import Image

def get_meta_data(path):
    data = path.stat()
    size = data.st_size
    mtime =data.st_mtime
    with Image.open(path) as img:
        width, height = img.size
        fmt = img.format
    result = {"size":size,"mtime":mtime,"width":width,"height":height,"format":fmt}
    return result
if __name__ == "__main__":
    print(get_meta_data(Path("data/2222.jpeg")))
    
