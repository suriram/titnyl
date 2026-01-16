from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import List
import os
from titnyl_parser import convert_tit_nyl_to_geojson
import uvicorn

app = FastAPI(title="TIT-NYL to GeoJSON Converter")

# Serverer statiske filer (HTML frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

@app.post("/convert")
async def convert_files(
    tit_files: List[UploadFile] = File(...),
    nyl_files: List[UploadFile] = File(...),
    epsg: str = Form("auto"),
    smooth: bool = Form(True)
):
    try:
        # Hjelpefunksjon for å lese innhold sikkert
        async def read_content(file: UploadFile) -> str:
            content_bytes = await file.read()
            try:
                return content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                return content_bytes.decode('latin-1')

        # Hjelpefunksjon for å få filnavn uten filtype
        def get_stem(filename: str) -> str:
            base = os.path.basename(filename)
            return os.path.splitext(base)[0].lower()

        # Last inn TIT-filer
        tit_map = {}
        for tf in tit_files:
            if tf.filename is None:
                continue
            stem = get_stem(tf.filename)
            tit_map[stem] = (tf.filename, await read_content(tf))

        # Last inn NYL-filer
        nyl_map = {}
        for nf in nyl_files:
            if nf.filename is None:
                continue
            stem = get_stem(nf.filename)
            nyl_map[stem] = await read_content(nf)

        # Match og prosesser
        all_features = []
        
        # Iterer over nøkler som finnes i begge mappene
        common_keys = set(tit_map.keys()) & set(nyl_map.keys())
        
        if not common_keys:
             return {
                "message": "Ingen matching funnet. tit og nyl filer må ha samme navn.",
                "type": "FeatureCollection",
                "features": []
             }

        for key in common_keys:
            original_filename, tit_content = tit_map[key]
            nyl_content = nyl_map[key]
            
            # Konverter
            result = convert_tit_nyl_to_geojson(
                tit_content, 
                nyl_content, 
                epsg=epsg, 
                filename=original_filename,
                smooth=smooth
            )
            
            # Samle features
            if result.get("features"):
                all_features.extend(result["features"])
        
        return {
            "type": "FeatureCollection",
            "features": all_features
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
