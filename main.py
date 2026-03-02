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
    """
    Recebe a URL de um vídeo do YouTube, baixa apenas o áudio
    e o converte para MP3, salvando-o na pasta 'downloads/'.

    - **url**: link completo do vídeo no YouTube.
    """

    if not YT_DLP_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Biblioteca yt-dlp não está instalada no servidor.",
        )

    # Opções do yt-dlp: extrair melhor áudio disponível e converter para MP3
    opcoes_ydl = {
        # Template do nome do arquivo de saída (sem extensão – o postprocessor adiciona .mp3)
        "outtmpl": str(DOWNLOADS_DIR / "%(title)s.%(ext)s"),

        # Seleciona apenas o melhor áudio disponível
        "format": "bestaudio/best",

        # Pós-processadores: converte o áudio para MP3 usando ffmpeg
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",  # kbps
            }
        ],

        # Silencia a saída padrão do yt-dlp
        "quiet": True,
        "no_warnings": True,
    }

    caminho_arquivo: str | None = None

    # Hook para capturar o caminho do arquivo gerado após o download
    def progresso_hook(d: dict) -> None:
        nonlocal caminho_arquivo
        if d.get("status") == "finished":
            # 'filename' aponta para o arquivo antes da conversão;
            # após o postprocessor, a extensão muda para .mp3
            caminho_arquivo = d.get("filename", "")

    opcoes_ydl["progress_hooks"] = [progresso_hook]

    try:
        with yt_dlp.YoutubeDL(opcoes_ydl) as ydl:
            ydl.download([payload.url])
    except yt_dlp.utils.DownloadError as exc:
        # Erro de download: URL inexistente, vídeo privado, região bloqueada, etc.
        raise HTTPException(
            status_code=422,
            detail=f"Falha ao baixar o vídeo: {str(exc)}",
        ) from exc
    except Exception as exc:
        # Qualquer outro erro inesperado
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao processar o download: {str(exc)}",
        ) from exc

    # Ajusta a extensão para .mp3 caso o hook tenha capturado o nome original
    if caminho_arquivo:
        caminho_mp3 = str(Path(caminho_arquivo).with_suffix(".mp3"))
    else:
        # Fallback: busca o MP3 mais recente na pasta downloads
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
# Health-check (opcional)
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
async def raiz() -> dict:
    """Verifica se a API está no ar."""
    return {"status": "ok", "mensagem": "YouTube Audio Downloader API está funcionando."}