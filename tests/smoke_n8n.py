"""Exercita um webhook publicado e confere a persistência das filas."""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8000"
WEBHOOK = "http://127.0.0.1:5678/webhook/classificar-mensagem"


def enviar(url, dados=None):
    if dados is None:
        req = Request(url)
    else:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=corpo, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=65) as resposta:
            return resposta.status, json.load(resposta)
    except HTTPError as resposta:
        with resposta:
            return resposta.code, json.load(resposta)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modo", choices=("demo", "ollama"), default="demo")
    modo = parser.parse_args().modo
    origem_esperada = {"demo": "demonstracao", "ollama": "ollama"}[modo]
    status, health = enviar(f"{API}/health")
    assert status == 200 and health["modo"] == modo, health

    for mensagem, categoria, fila in (
        ("Qual o preço do plano?", "duvida", "comercial"),
        ("Podem emitir a segunda via do boleto?", "solicitacao", "financeiro"),
        ("O sistema caiu e a loja não consegue vender.", "reclamacao", "prioritario"),
        ("Meu pedido passou do prazo. Podem verificar?", "reclamacao", "operacoes"),
        ("Olá", "outro", "triagem"),
    ):
        status, recibo = enviar(WEBHOOK, {"mensagem": mensagem})
        assert status == 201, (status, recibo)
        assert recibo["fila"] == fila and recibo["classificacao"]["categoria"] == categoria, recibo
        assert recibo["origem"] == origem_esperada, recibo
        status, encontrados = enviar(f"{API}/encaminhamentos?fila={fila}")
        assert status == 200, encontrados
        assert any(item["id"] == recibo["id"] and item["mensagem"] == mensagem for item in encontrados), recibo
        print(f"{categoria} -> {fila}: HTTP 201, origem {origem_esperada} e registro consultado")

    status, erro = enviar(WEBHOOK, {"mensagem": " "})
    assert status == 422 and erro["erro"] == "entrada_invalida", (status, erro)
    print("entrada inválida: HTTP 422")


if __name__ == "__main__":
    main()
