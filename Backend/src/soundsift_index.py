import os
import numpy as np
import librosa
import laion_clap
from typing import List
import re

from db import (
    init_db,
    get_sample_by_path,
    upsert_sample,
    insert_sample,
    store_embedding,
    store_text_embedding,
    blob_to_np,
    get_connection,
    get_sample_by_index
)

# -----------------------------
# Config
# -----------------------------

SAMPLE_RATE = 48000
SUPPORTED_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3"}
MODEL_VERSION = "default"
EMBED_DIM = 512
EMBEDDINGS_PATH = "data/embeddings.bin"


# -----------------------------
# Utils
# -----------------------------

def find_audio_files(root: str) -> List[str]:
    files = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS:
                files.append(os.path.join(dirpath, f))
    return files


def load_audio_mono(path: str, max_seconds: float) -> np.ndarray:
    audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    return audio[: int(SAMPLE_RATE * max_seconds)]


def cosine_similarity_matrix(query: np.ndarray, vectors: np.ndarray):
    print(vectors)
    query = query / np.linalg.norm(query)
    # vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors @ query

def path_to_text(path: str) -> str:
    parts = os.path.normpath(path).split(os.sep)

    tokens = []
    for p in parts:
        p = os.path.splitext(p)[0]
        p = re.sub(r"[_\-]", " ", p)
        tokens.append(p.lower())

    return " ".join(tokens)

def normalize_vector(v):
    norm = np.linalg.norm(v)
    if norm == 0: 
        return v
    return v / norm



# -----------------------------
# Main Index Class
# -----------------------------

class SoundSiftIndex:
    def __init__(self):
        init_db()

        self.model = laion_clap.CLAP_Module(enable_fusion=False)
        self.model.load_ckpt()

        self.paths: List[str] = []
        self.embeddings = None
        self.loaded = False
        

    def load(self):
        if not os.path.exists(EMBEDDINGS_PATH):
            self.embeddings = None
            return

        file_size = os.path.getsize(EMBEDDINGS_PATH)
        n_rows = file_size // (EMBED_DIM * 4) # 4 bytes per float32
        # print(n_rows)
        
        if n_rows == 0:
            self.embeddings = None
            return

        self.embeddings = np.memmap(
            EMBEDDINGS_PATH, 
            dtype='float32', 
            mode='r', 
            shape=(n_rows, EMBED_DIM)
        )

    # Not needed in new arch
    def ensure_loaded(self):
        if not self.loaded:
            self.load_embeddings()
            self.load_text_embeddings()
            self.loaded = True

    # ---------- INDEXING ----------

    def index_file(self, path: str, max_seconds: float = 10.0) -> bool:
        stat = os.stat(path)
        mtime = stat.st_mtime

        existing = get_sample_by_path(path)
        if existing and existing[1] == mtime:
            self.index_text(sample_id, path)
            return False  # unchanged

        audio = load_audio_mono(path, max_seconds)
        duration = len(audio) / SAMPLE_RATE
        audio = audio.reshape(1, -1)

        emb = self.model.get_audio_embedding_from_data(
            x=audio,
            use_tensor=False
        )[0]
        print(emb.shape)

        sample_id = upsert_sample(path, mtime, duration)
        store_embedding(sample_id, MODEL_VERSION, emb)

        self.index_text(sample_id, path)

        return True

    def index_folder(self, folder: str):
        files = find_audio_files(folder)
        embedded = 0

        for path in files:
            try:
                if self.index_file(path):
                    embedded += 1
            except Exception as e:
                print(f"Failed {path}: {e}")

        print(f"Embedded {embedded} new/changed files")
        return embedded
    
    def index_folder2(self, folder: str):
        dtype = np.float32
        itemsize = 4 * EMBED_DIM

        all_files = find_audio_files(folder)
        new_files = []
        
        # This check is important. Only add files we haven't indexed yet.
        for f in all_files:
            if not get_sample_by_path(f): # Check DB
                new_files.append(f)
        
        N_new = len(new_files)
        if N_new == 0:
            print("No new files to index.")
            return

        N_old = 0
        if os.path.exists(EMBEDDINGS_PATH):
            file_size = os.path.getsize(EMBEDDINGS_PATH)
        N_old = file_size // itemsize
        N_total = N_old + N_new

        temp_emb_path = EMBEDDINGS_PATH + ".tmp"
        with open(temp_emb_path, "wb") as file:
            file.truncate(N_total * itemsize)

        # memmap for the new file. allocating n_total vectors
        new_emb_mmap = np.memmap(
            temp_emb_path, 
            dtype=dtype, 
            mode='r+', 
            shape=(N_total, EMBED_DIM)
        )

        if N_old > 0:
            # We assume the old file is valid. 
            # We map it read-only to copy quickly.
            old_mmap = np.memmap(
                EMBEDDINGS_PATH, 
                dtype=dtype, 
                mode='r', 
                shape=(N_old, EMBED_DIM)
            )
            
            # Bulk copy: Extremely fast (essentially a `memcpy` in C)
            new_emb_mmap[0:N_old] = old_mmap[:]
        
            # Close old map so we can delete the file later if needed
            del old_mmap
        
        start_idx = N_old

        for i, path in enumerate(new_files):
            try:
                # Load & Embed
                audio = load_audio_mono(path, 10.0) # Reduced to 10s for speed
                if len(audio) == 0: continue 

                audio = audio.reshape(1, -1)
                emb = self.model.get_audio_embedding_from_data(x=audio, use_tensor=False)[0]
                
                # Write to Binary (Normalized)
                cur_idx = start_idx + i
                new_emb_mmap[cur_idx] = normalize_vector(emb).astype(dtype)

                # Update DB
                # Note: get stat info again or cache it from step 1
                stat = os.stat(path)
                duration = len(audio[0]) / SAMPLE_RATE
                insert_sample(path, cur_idx, stat.st_mtime, duration)
                
                # Also index text metadata
                # self.index_text(upsert_sample(path, stat.st_mtime, duration), path)

            except Exception as e:
                print(f"Error indexing {path}: {e}")

        new_emb_mmap.flush()
        del new_emb_mmap # Close the file handle
        
        # Atomic Swap: Replace old file with new file
        if os.path.exists(EMBEDDINGS_PATH):
            os.remove(EMBEDDINGS_PATH)
        os.rename(temp_emb_path, EMBEDDINGS_PATH)

        return new_files


    # Text embeddings
    def index_text(self, sample_id: int, path: str):
        text = path_to_text(path)
        print(text)
        emb = self.model.get_text_embedding([text])[0]
        store_text_embedding(sample_id, MODEL_VERSION, emb)

    # ---------- LOAD FOR SEARCH ----------

    def load_embeddings(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT samples.path, embeddings.vector
        FROM embeddings
        JOIN samples ON samples.id = embeddings.sample_id
        WHERE embeddings.model_version = ?
        """, (MODEL_VERSION,))

        paths = []
        vectors = []

        for path, blob in cur.fetchall():
            paths.append(path)
            vectors.append(blob_to_np(blob, EMBED_DIM))
        conn.close()

        # print(paths, vectors)
        if vectors:
            self.paths = paths
            self.embeddings = np.vstack(vectors)
        else:
            self.paths = []
            self.embeddings = None

    def load_text_embeddings(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT samples.path, text_embeddings.vector
        FROM text_embeddings
        JOIN samples ON samples.id = text_embeddings.sample_id
        WHERE text_embeddings.model_version = ?
        """, (MODEL_VERSION,))

        paths = []
        vectors = []

        for path, blob in cur.fetchall():
            paths.append(path)
            vectors.append(blob_to_np(blob, EMBED_DIM))

        conn.close()

        if vectors:
            self.text_paths = paths
            self.text_embeddings = np.vstack(vectors)
        else:
            self.text_paths = []
            self.text_embeddings = None

    # ---------- QUERY ----------

    def query(
        self,
        text: str,
        top_k: int = 10,
        audio_weight: float = 1,
        text_weight: float = 0.3,
    ):
        
        self.load()

        if self.embeddings is None or len(self.embeddings) == 0:
            return []
        
        # 1. Embed query text
        q_emb = self.model.get_text_embedding([text])[0]
        # print("q", q_emb)

        # 2. Similarity against audio
        audio_sims = cosine_similarity_matrix(q_emb, self.embeddings)
        print('asims', audio_sims)

        # 3. Similarity against text-derived embeddings
        # text_sims = cosine_similarity_matrix(q_emb, self.text_embeddings)

        # 4. Combine
        sims = (
            audio_weight * audio_sims
        )

        # print(sims)

        # 5. Rank
        idxs = np.argsort(-sims)[:top_k]
        print(idxs)

        return [
            {
                "score": float(sims[i]),
                "audio_score": float(audio_sims[i]),
                # "text_score": float(text_sims[i]),
                "path": get_sample_by_index(i),
            }
            for i in idxs
        ]



# -----------------------------
# Example usage
# -----------------------------

if __name__ == "__main__":
    index = SoundSiftIndex()

    SAMPLE_FOLDER = "/Users/kierankhan/Dev/Sound Sift 2/Samples"

    index.index_folder(SAMPLE_FOLDER)
    index.load_embeddings()

    results = index.query("heavy distorted snare", top_k=5)
    for score, path in results:
        print(f"{score:.3f}  {os.path.basename(path)}")
