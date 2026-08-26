from pathlib import Path
from PIL import Image
from hash import hasher

def iter_files(root):
    for path in root.rglob("*"):
        if path.is_file():
            yield path

def is_image(path):
    try:
        with Image.open(path) as img:
            return True, img.format
    except Exception:
        return False, None        
        
        
        
    

if __name__=="__main__":
    root = Path("data")
    for path in iter_files(root):
        ok , fmt=is_image(path)
        if ok:
            obj=hasher(path)
        else:
            obj = None
        print(ok, fmt, path,obj)
    
   