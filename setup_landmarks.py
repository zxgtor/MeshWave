"""Fetch the official model once; inference itself never downloads or uploads images."""
import hashlib
from pathlib import Path
import urllib.request
from landmarks import MODEL_SHA256

URL='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task'
if __name__=='__main__':
    destination=Path(__file__).parent/'models'/'face_landmarker.task'
    with urllib.request.urlopen(URL,timeout=60) as response:
        data=response.read(10_000_000)
    if hashlib.sha256(data).hexdigest()!=MODEL_SHA256:
        raise SystemExit('Model checksum mismatch; no installed model was replaced.')
    destination.parent.mkdir(exist_ok=True)
    temporary=destination.with_suffix('.download')
    temporary.write_bytes(data);temporary.replace(destination)
    print(f'Model ready: {destination}')
