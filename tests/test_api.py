import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import UUID

import httpx
from fastapi.testclient import TestClient

from app.main import Config, criar_app

BOLETO = "Podem emitir a segunda via do boleto?"
SAIDA = {
    "categoria": "solicitacao",
    "prioridade": "media",
    "resumo": "Cliente solicita a segunda via do boleto.",
    "setor_sugerido": "financeiro",
}


def conclusao(conteudo, *, motivo="stop"):
    return httpx.Response(200, json={"done": True, "done_reason": motivo, "message": {"content": conteudo}})


class TestAPI(TestCase):
    def setUp(self):
        pasta = self.enterContext(TemporaryDirectory())
        self.db = Path(pasta) / "fila.sqlite3"

    def cliente(self, provedor=None):
        if provedor is None:
            return TestClient(criar_app(Config(db_path=self.db)))
        config = Config(db_path=self.db, modo="ollama", ollama_base_url="http://ollama:11434/")
        return TestClient(criar_app(config, transporte=httpx.MockTransport(provedor)))

    def test_health(self):
        with self.cliente() as cliente:
            self.assertEqual(cliente.get("/health").json(), {"status": "ok", "modo": "demo"})

    def test_rejeita_entrada_invalida(self):
        with self.cliente() as cliente:
            for dados in ({}, {"mensagem": " \n "}, {"mensagem": 123}, {"mensagem": "x" * 3001},
                          {"mensagem": "Olá", "origem": "ollama"}):
                with self.subTest(dados=dados):
                    resposta = cliente.post("/classificacoes", json=dados)
                    self.assertEqual(resposta.status_code, 422)
                    self.assertEqual(resposta.json()["erro"], "entrada_invalida")
                    for campo in resposta.json()["campos"]:
                        self.assertEqual(set(campo), {"campo", "tipo"})

    def test_rejeita_json_malformado(self):
        with self.cliente() as cliente:
            resposta = cliente.post("/classificacoes", content="{", headers={"Content-Type": "application/json"})
            self.assertEqual(resposta.status_code, 422)
            self.assertEqual(resposta.json()["erro"], "entrada_invalida")

    def test_demonstracao(self):
        with self.cliente() as cliente:
            for mensagem, categoria, prioridade, setor in (
                ("Qual é o preço do plano?", "duvida", "baixa", "comercial"),
                (BOLETO, "solicitacao", "media", "financeiro"),
                ("Meu pedido passou do prazo. Podem verificar?", "reclamacao", "media", "operacoes"),
                ("O sistema caiu e a loja não consegue vender.", "reclamacao", "alta", "suporte"),
                ("Urgente!", "outro", "baixa", "atendimento"),
            ):
                with self.subTest(mensagem=mensagem):
                    resposta = cliente.post("/classificacoes", json={"mensagem": mensagem})
                    self.assertEqual(resposta.status_code, 200)
                    dados = resposta.json()
                    self.assertEqual(UUID(dados["id"]).version, 4)
                    self.assertEqual(dados["origem"], "demonstracao")
                    classificacao = dados["classificacao"]
                    self.assertEqual(classificacao["categoria"], categoria)
                    self.assertEqual(classificacao["prioridade"], prioridade)
                    self.assertEqual(classificacao["setor_sugerido"], setor)

    def test_ollama_envia_schema_sem_chave_e_registra_origem(self):
        def provedor(request):
            self.assertEqual(str(request.url), "http://ollama:11434/api/chat")
            self.assertNotIn("Authorization", request.headers)
            corpo = json.loads(request.content)
            self.assertEqual(corpo["model"], "qwen3:1.7b")
            self.assertEqual(corpo["messages"][0]["role"], "system")
            self.assertEqual(corpo["messages"][1], {"role": "user", "content": BOLETO})
            self.assertFalse(corpo["stream"])
            self.assertFalse(corpo["think"])
            self.assertEqual(set(corpo["format"]["required"]), set(SAIDA))
            self.assertFalse(corpo["format"]["additionalProperties"])
            return conclusao(json.dumps(SAIDA))

        with self.cliente(provedor) as cliente:
            self.assertEqual(cliente.get("/health").json()["modo"], "ollama")
            resposta = cliente.post("/classificacoes", json={"mensagem": BOLETO})
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.json()["origem"], "ollama")
            self.assertEqual(resposta.json()["classificacao"], SAIDA)
            dados = resposta.json() | {"fila": "financeiro", "mensagem": BOLETO}
            recibo = cliente.post("/encaminhamentos", json=dados)
            self.assertEqual(recibo.status_code, 201)
            self.assertEqual(recibo.json()["origem"], "ollama")

    def test_erro_do_motor_vai_para_revisao(self):
        def timeout(request):
            raise httpx.ReadTimeout("timeout de teste", request=request)

        respostas = {
            "json": conclusao("texto solto"),
            "categoria": conclusao(json.dumps(SAIDA | {"categoria": "spam"})),
            "resumo": conclusao(json.dumps(SAIDA | {"resumo": " "})),
            "campo_extra": conclusao(json.dumps(SAIDA | {"fila": "prioritario"})),
            "conteudo_ausente": conclusao(None),
            "truncado": conclusao("{", motivo="length"),
            "404": httpx.Response(404, json={"error": "modelo ausente"}),
        }
        provedores = {caso: (lambda _, resp=resposta: resp) for caso, resposta in respostas.items()}
        provedores["timeout"] = timeout
        for caso, provedor in provedores.items():
            with self.subTest(caso=caso), self.cliente(provedor) as cliente:
                resposta = cliente.post("/classificacoes", json={"mensagem": BOLETO})
                self.assertEqual(resposta.status_code, 200)
                dados = resposta.json()
                self.assertEqual(dados["origem"], "fallback")
                self.assertEqual(dados["classificacao"]["categoria"], "outro")
                self.assertEqual(dados["classificacao"]["prioridade"], "media")
                self.assertNotIn(BOLETO, resposta.text)

    def test_ollama_sem_modelo_interrompe_startup(self):
        config = Config(db_path=self.db, modo="ollama", ollama_model="")
        with self.assertRaisesRegex(RuntimeError, "OLLAMA_MODEL"), TestClient(criar_app(config)):
            pass

    def test_fila_persistencia_repeticao_e_conflito(self):
        with self.cliente() as cliente:
            classificacao = cliente.post("/classificacoes", json={"mensagem": BOLETO}).json()
            dados = classificacao | {"fila": "financeiro", "mensagem": BOLETO}
            primeiro = cliente.post("/encaminhamentos", json=dados)
            self.assertEqual(primeiro.status_code, 201)
            self.assertNotIn("mensagem", primeiro.json())
            repetido = cliente.post("/encaminhamentos", json=dados)
            self.assertEqual(repetido.status_code, 200)
            self.assertEqual(repetido.json(), primeiro.json())
            conflito = cliente.post("/encaminhamentos", json=dados | {"fila": "triagem"})
            self.assertEqual(conflito.status_code, 409)
            self.assertEqual(cliente.get("/encaminhamentos", params={"fila": "qualquer"}).status_code, 422)

        with self.cliente() as cliente:
            lista = cliente.get("/encaminhamentos", params={"fila": "financeiro"}).json()
            self.assertEqual(lista, [primeiro.json() | {"mensagem": BOLETO}])
            self.assertEqual(cliente.get("/encaminhamentos", params={"fila": "triagem"}).json(), [])
