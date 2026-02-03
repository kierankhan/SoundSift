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
    store_embedding,
    store_text_embedding,
    blob_to_np,
    get_connection
)

# -----------------------------
# Config
# -----------------------------

SAMPLE_RATE = 48000
SUPPORTED_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3"}
MODEL_VERSION = "default"
EMBED_DIM = 512


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
    query = query / np.linalg.norm(query)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors @ query

def path_to_text(path: str) -> str:
    parts = os.path.normpath(path).split(os.sep)

    tokens = []
    for p in parts:
        p = os.path.splitext(p)[0]
        p = re.sub(r"[_\-]", " ", p)
        tokens.append(p.lower())

    return " ".join(tokens)



# -----------------------------
# Main Index Class
# -----------------------------

class SoundSiftIndex:
    def __init__(self):
        init_db()

        self.model = laion_clap.CLAP_Module(enable_fusion=False)
        self.model.load_ckpt()

        self.paths: List[str] = []
        self.embeddings: np.ndarray | None = None
        self.loaded = False

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
        audio_weight: float = 0.7,
        text_weight: float = 0.3,
    ):
        if self.embeddings is None:
            raise RuntimeError("Audio embeddings not loaded.")
        if not hasattr(self, "text_embeddings") or self.text_embeddings is None:
            raise RuntimeError("Text embeddings not loaded.")

        # 1. Embed query text
        q_emb = self.model.get_text_embedding([text])[0]

        # 2. Similarity against audio
        audio_sims = cosine_similarity_matrix(q_emb, self.embeddings)

        # 3. Similarity against text-derived embeddings
        text_sims = cosine_similarity_matrix(q_emb, self.text_embeddings)

        # 4. Combine
        sims = (
            audio_weight * audio_sims
            + text_weight * text_sims
        )

        # 5. Rank
        idxs = np.argsort(-sims)[:top_k]

        return [
            {
                "score": float(sims[i]),
                "audio_score": float(audio_sims[i]),
                "text_score": float(text_sims[i]),
                "path": self.paths[i],
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
