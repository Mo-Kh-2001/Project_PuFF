import sqlite3

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS pictures (
                       sha256 TEXT PRIMARY KEY,
                       width INTEGER,
                       height INTEGER,
                       format TEXT
                   )
                   """)
    conn.commit()
    return conn






if __name__ == "__main__":
    init_db("puff.db")