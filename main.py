"""
API REST com FastAPI para download de áudio de vídeos do YouTube.
Utiliza yt-dlp para extrair e salvar o áudio em formato MP3.

Instalação das dependências:
    pip install fastapi uvicorn yt-dlp

Execução:
    uvicorn main:app --reload
"""

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# Tentativa de importar yt_dlp (opcional para facilitar testes sem a lib)
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------------

# Pasta onde os arquivos MP3 serão salvos
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Inicialização da aplicação FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="YouTube Audio Downloader",
    description="API para baixar áudio de vídeos do YouTube em formato MP3.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — deve ser registrado logo após criar o app
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # em produção, coloque a URL do seu Vercel
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Modelos de dados (Pydantic)
# ---------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    """Corpo da requisição: apenas a URL do vídeo."""
    url: str

    @field_validator("url")
    @classmethod
    def validar_url(cls, v: str) -> str:
        """Valida se a URL parece ser um link válido do YouTube."""
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
    """Corpo da resposta em caso de sucesso."""
    mensagem: str
    arquivo: str


# ---------------------------------------------------------------------------
# Endpoint principal
# ---------------------------------------------------------------------------

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

    opcoes_ydl = {
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),
        "format": "bestaudio/best",
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

    return DownloadResponse(
        mensagem="Áudio baixado e convertido com sucesso!",
        arquivo=caminho_mp3,
    )


# ---------------------------------------------------------------------------
# Health-check
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
async def raiz() -> dict:
    return {"status": "ok", "mensagem": "YouTube Audio Downloader API está funcionando."}