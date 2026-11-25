from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints


class Categoria(StrEnum):
    DUVIDA = "duvida"
    RECLAMACAO = "reclamacao"
    SOLICITACAO = "solicitacao"
    OUTRO = "outro"


class Prioridade(StrEnum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class Setor(StrEnum):
    ATENDIMENTO = "atendimento"
    COMERCIAL = "comercial"
    FINANCEIRO = "financeiro"
    OPERACOES = "operacoes"
    SUPORTE = "suporte"


class Fila(StrEnum):
    ATENDIMENTO = Setor.ATENDIMENTO
    COMERCIAL = Setor.COMERCIAL
    FINANCEIRO = Setor.FINANCEIRO
    OPERACOES = Setor.OPERACOES
    SUPORTE = Setor.SUPORTE
    PRIORITARIO = "prioritario"
    TRIAGEM = "triagem"


class Origem(StrEnum):
    OLLAMA = "ollama"
    DEMONSTRACAO = "demonstracao"
    FALLBACK = "fallback"


class Contrato(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mensagem(Contrato):
    mensagem: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]


class CampoInvalido(Contrato):
    campo: str
    tipo: str


class EntradaInvalida(Contrato):
    erro: Literal["entrada_invalida"] = "entrada_invalida"
    campos: list[CampoInvalido]


class Classificacao(Contrato):
    categoria: Categoria
    prioridade: Prioridade
    resumo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
    setor_sugerido: Setor


class Resultado(Contrato):
    id: UUID
    origem: Origem
    classificacao: Classificacao


class Encaminhamento(Resultado, Mensagem):
    fila: Fila


class Comprovante(Resultado):
    fila: Fila
    registrado_em: str


class Registro(Comprovante, Mensagem):
    pass


def schema_classificacao() -> dict:
    schema = Classificacao.model_json_schema()
    # As restrições de comprimento também são aplicadas localmente pelo Pydantic.
    for chave in ("title", "minLength", "maxLength"):
        schema["properties"]["resumo"].pop(chave, None)
    return schema
