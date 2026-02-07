from pydantic import BaseModel
from fastapi import FastAPI
import soundsift_index


app = FastAPI()
Index = soundsift_index.SoundSiftIndex()

class SampleFolder(BaseModel):
    file_path: str

class Query(BaseModel):
    text: str
    top_k: int

@app.post("/index/folder")
async def index(sample_folder: SampleFolder):
    try:
        changed = Index.index_folder2(sample_folder.file_path)
        Index.loaded = False
        return {'status': 'ok', 'files_embedded': changed}
    except:
        print('Failed')
        return {'status': 'error', 'files_embedded': changed if changed else 0}

@app.post("/query/text")
async def index(query: Query):
    # Index.ensure_loaded()
    results = Index.query(query.text, top_k=query.top_k)
    return {"results": results}

@app.post("/load")
async def load():
    Index.ensure_loaded()