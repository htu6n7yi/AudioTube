
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="YouTube Audio Downloader",
    description="API para baixar áudio de vídeos do YouTube em formato MP3.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")


class DownloadRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validar_url(cls, v: str) -> str:
        v = v.strip()
        padrao_youtube = re.compile(
            r"(https?://)?(www\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)"
            r"[\w\-]+"
        )
        if not padrao_youtube.search(v):
            raise ValueError(
                "URL inválida. Informe um link válido do YouTube "
                "(ex: https://www.youtube.com/watch?v=...)"
            )
        return v


class DownloadResponse(BaseModel):
    mensagem: str
    arquivo: str


@app.post(
    "/download-audio",
    response_model=DownloadResponse,
    summary="Baixar áudio de um vídeo do YouTube",
    status_code=200,
)
async def download_audio(payload: DownloadRequest) -> DownloadResponse:
    if not YT_DLP_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Biblioteca yt-dlp não está instalada no servidor.",
        )

    agora = time.time()
    for arquivo in DOWNLOADS_DIR.glob("*"):
        try:
            if agora - arquivo.stat().st_mtime > 600:
                arquivo.unlink()
        except Exception as e:
            print(f"Erro ao tentar limpar arquivo antigo: {e}")
            pass

    opcoes_ydl = {
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),
        "format": "bestaudio/best",

        # ALTERAÇÃO PARA EVITAR BLOQUEIO DO YOUTUBE NO RENDER
        "extractor_args": {"youtube": {"player_client": ["android"]}},

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    caminho_arquivo: str | None = None

    def progresso_hook(d: dict) -> None:
        nonlocal caminho_arquivo
        if d.get("status") == "finished":
            caminho_arquivo = d.get("filename", "")

    opcoes_ydl["progress_hooks"] = [progresso_hook]

    try:
        with yt_dlp.YoutubeDL(opcoes_ydl) as ydl:
            ydl.download([payload.url])
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Falha ao baixar o vídeo: {str(exc)}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao processar o download: {str(exc)}",
        ) from exc

    if caminho_arquivo:
        caminho_mp3 = str(Path(caminho_arquivo).with_suffix(".mp3"))
    else:
        arquivos = sorted(
            DOWNLOADS_DIR.glob("*.mp3"),
            key=os.path.getmtime,
            reverse=True,
        )
        if not arquivos:
            raise HTTPException(
                status_code=500,
                detail="Download concluído, mas o arquivo MP3 não foi encontrado.",
            )
        caminho_mp3 = str(arquivos[0])

    caminho_web = caminho_mp3.replace("\\", "/")

    return DownloadResponse(
        mensagem="Áudio baixado e convertido com sucesso!",
        arquivo=caminho_web,
    )


@app.get("/", summary="Health check")
async def raiz() -> dict:
    return {"status": "ok", "mensagem": "YouTube Audio Downloader API está funcionando."}