import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .schemas import Encaminhamento, Fila, Registro


class ConflitoDeEncaminhamento(Exception):
    pass


class FilaSQLite:
    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho

    @contextmanager
    def conectar(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.caminho, timeout=3)) as conexao:
            conexao.row_factory = sqlite3.Row
            with conexao:
                yield conexao

    def iniciar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.conectar() as conexao:
            conexao.execute("PRAGMA journal_mode=WAL")
            conexao.execute("""
                CREATE TABLE IF NOT EXISTS encaminhamentos (
                    id TEXT PRIMARY KEY,
                    fila TEXT NOT NULL,
                    registrado_em TEXT NOT NULL,
                    dados TEXT NOT NULL
                )
            """)
            conexao.execute("""
                CREATE INDEX IF NOT EXISTS encaminhamentos_fila_data
                ON encaminhamentos (fila, registrado_em DESC, id DESC)
            """)

    def salvar(self, item: Encaminhamento) -> tuple[Registro, bool]:
        with self.conectar() as conexao:
            registro = Registro(**item.model_dump(), registrado_em=datetime.now(UTC).isoformat())
            insercao = conexao.execute(
                "INSERT INTO encaminhamentos VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (str(item.id), item.fila, registro.registrado_em, registro.model_dump_json()),
            )
            if insercao.rowcount:
                return registro, True
            linha = conexao.execute(
                "SELECT dados FROM encaminhamentos WHERE id = ?", (str(item.id),)
            ).fetchone()
            anterior = Registro.model_validate_json(linha["dados"])
            if anterior.model_dump(exclude={"registrado_em"}) != item.model_dump():
                raise ConflitoDeEncaminhamento
            return anterior, False

    def listar(self, fila: Fila, limite: int) -> list[Registro]:
        with self.conectar() as conexao:
            linhas = conexao.execute(
                "SELECT dados FROM encaminhamentos WHERE fila = ? ORDER BY registrado_em DESC, id DESC LIMIT ?",
                (fila, limite),
            ).fetchall()
            return [Registro.model_validate_json(linha["dados"]) for linha in linhas]
