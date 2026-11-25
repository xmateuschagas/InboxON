import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .classifier import classificar, criar_motor
from .queue import ConflitoDeEncaminhamento, FilaSQLite
from .schemas import CampoInvalido, Comprovante, Encaminhamento, EntradaInvalida, Fila, Mensagem, Registro, Resultado

log = logging.getLogger("uvicorn.error.inboxon")
ERRO_422 = {422: {"description": "Entrada inválida", "model": EntradaInvalida}}


@dataclass(frozen=True)
class Config:
    db_path: Path = Path("data/encaminhamentos.sqlite3")
    modo: Literal["demo", "ollama"] = "demo"
    ollama_model: str = "qwen3:1.7b"
    ollama_base_url: str = "http://127.0.0.1:11434/"

    @classmethod
    def carregar(cls) -> "Config":
        load_dotenv()
        modo = os.getenv("CLASSIFIER_MODE", "demo").strip().lower()
        if modo not in {"demo", "ollama"}:
            raise ValueError("CLASSIFIER_MODE deve ser demo ou ollama")
        return cls(
            db_path=Path(os.getenv("DATABASE_PATH", str(cls.db_path))),
            modo=modo,
            ollama_model=os.getenv("OLLAMA_MODEL", cls.ollama_model).strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url).strip(),
        )


def criar_app(config: Config | None = None, *, transporte: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        cfg = config or Config.carregar()
        if cfg.modo == "ollama" and (not cfg.ollama_model or not cfg.ollama_base_url):
            raise RuntimeError("Configure OLLAMA_MODEL e OLLAMA_BASE_URL para o modo ollama")
        api.state.fila = FilaSQLite(cfg.db_path)
        api.state.fila.iniciar()
        api.state.modo = cfg.modo
        api.state.motor = None
        log.info("api_iniciada modo=%s", cfg.modo)
        if cfg.modo == "demo":
            yield
            return

        async with httpx.AsyncClient(
            base_url=cfg.ollama_base_url,
            timeout=httpx.Timeout(42.0, connect=3.0),
            trust_env=False,
            transport=transporte,
        ) as cliente:
            api.state.motor = criar_motor(cliente, cfg.ollama_model)
            yield

    api = FastAPI(title="InboxON | Classificação e roteamento de mensagens", version="1.1.0", lifespan=lifespan)

    @api.exception_handler(RequestValidationError)
    async def entrada_invalida(_: Request, erro: RequestValidationError) -> JSONResponse:
        campos = [CampoInvalido(campo=".".join(map(str, item["loc"])), tipo=item["type"]) for item in erro.errors()]
        return JSONResponse(status_code=422, content=EntradaInvalida(campos=campos).model_dump())

    @api.exception_handler(sqlite3.OperationalError)
    async def fila_indisponivel(_: Request, erro: sqlite3.OperationalError) -> JSONResponse:
        log.error("fila_indisponivel codigo=%s", getattr(erro, "sqlite_errorname", "desconhecido"))
        return JSONResponse(status_code=503, content={"detail": "fila_indisponivel"})

    @api.get("/health", tags=["Operação"])
    def health() -> dict[str, str]:
        return {"status": "ok", "modo": api.state.modo}

    @api.post("/classificacoes", response_model=Resultado, tags=["Classificação"], responses=ERRO_422)
    async def classificar_mensagem(entrada: Mensagem) -> Resultado:
        identificador = uuid4()
        classificacao, origem = await classificar(entrada.mensagem, api.state.motor)
        log.info(
            "classificada id=%s origem=%s categoria=%s prioridade=%s",
            identificador, origem, classificacao.categoria, classificacao.prioridade,
        )
        return Resultado(id=identificador, origem=origem, classificacao=classificacao)

    @api.post(
        "/encaminhamentos", response_model=Comprovante, status_code=201, tags=["Filas"],
        responses={
            **ERRO_422,
            200: {"description": "Encaminhamento já registrado", "model": Comprovante},
            409: {"description": "ID já usado para outro encaminhamento"},
            503: {"description": "Fila indisponível"},
        },
    )
    def registrar(entrada: Encaminhamento, resposta: Response) -> Comprovante:
        try:
            registro, novo = api.state.fila.salvar(entrada)
        except ConflitoDeEncaminhamento:
            raise HTTPException(status_code=409, detail="id_ja_utilizado") from None
        if not novo:
            resposta.status_code = 200
        log.info("encaminhamento id=%s fila=%s novo=%s", entrada.id, entrada.fila, novo)
        return Comprovante(**registro.model_dump(exclude={"mensagem"}))

    @api.get("/encaminhamentos", response_model=list[Registro], tags=["Filas"], responses=ERRO_422)
    def listar(fila: Fila, limite: Annotated[int, Query(ge=1, le=100)] = 20) -> list[Registro]:
        return api.state.fila.listar(fila, limite)

    return api


app = criar_app()
