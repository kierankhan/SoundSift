import sqlite3
import os
import numpy as np

DB_PATH = "data/soundsift.db"

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS samples (
        id INTEGER PRIMARY KEY,
        path TEXT UNIQUE,
        vec_index INTEGER,
        mtime REAL,
        duration REAL
    )
    """)

    # cur.execute("""
    # CREATE TABLE IF NOT EXISTS embeddings (
    #     sample_id INTEGER,
    #     model_version TEXT,
    #     vector BLOB,
    #     FOREIGN KEY(sample_id) REFERENCES samples(id),
    #     UNIQUE(sample_id, model_version)
    # )
    # """)

    # TODO: Figure out how to do text embeddings in new arch
    # cur.execute("""
    # CREATE TABLE IF NOT EXISTS text_embeddings (
    #     sample_id INTEGER,
    #     model_version TEXT,
    #     vector BLOB,
    #     FOREIGN KEY(sample_id) REFERENCES samples(id),
    #     UNIQUE(sample_id, model_version)
    # );
    # """)

    conn.commit()
    conn.close()

def np_to_blob(arr: np.ndarray) -> bytes:
    return arr.astype(np.float32).tobytes()

def blob_to_np(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dim)


def get_sample_by_path(path: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, mtime FROM samples WHERE path = ?",
        (path,)
    )
    row = cur.fetchone()
    conn.close()
    return row

def get_sample_by_index(idx: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, path FROM samples WHERE vec_index = ?",
        (int(idx),)
    )
    row = cur.fetchone()
    conn.close()
    return row[1] if row else None

def insert_sample(path: str, index: int, mtime: float, duration: float) -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO samples (path, vec_index, mtime, duration)
        VALUES (?, ?, ?, ?)
        """, (path, index, mtime, duration))

        conn.commit()
        return True
    except:
        print("failed to insert")
        return False
    # cur.execute("SELECT id FROM samples WHERE path = ?", (path,))
    # sample_id = cur.fetchone()[0]
    # conn.close()

    # return sample_id

def upsert_sample(path: str, mtime: float, duration: float) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO samples (path, mtime, duration)
    VALUES (?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        mtime = excluded.mtime,
        duration = excluded.duration
    """, (path, mtime, duration))

    conn.commit()

    cur.execute("SELECT id FROM samples WHERE path = ?", (path,))
    sample_id = cur.fetchone()[0]
    conn.close()

    return sample_id


def store_embedding(sample_id: int, model_version: str, emb: np.ndarray):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO embeddings (sample_id, model_version, vector)
    VALUES (?, ?, ?)
    """, (sample_id, model_version, np_to_blob(emb)))

    conn.commit()
    conn.close()

def store_text_embedding(sample_id: int, model_version: str, emb: np.ndarray):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO text_embeddings (sample_id, model_version, vector)
    VALUES (?, ?, ?)
    """, (sample_id, model_version, np_to_blob(emb)))

    conn.commit()
    conn.close()