# InboxON

## Apresentação da Ideia

O InboxON surgiu da rotina de pequenas empresas que recebem dúvidas, reclamações e solicitações no mesmo canal. A proposta é automatizar a primeira triagem e deixar um registro consultável de cada encaminhamento.

## Problema Escolhido

O projeto resolve o caso **4.1 — Classificação de Mensagens** do desafio KODIE. A leitura e a distribuição manuais consomem tempo e podem atrasar pedidos urgentes. Esse caso permite verificar o resultado de ponta a ponta usando a mensagem original, a categoria atribuída e o registro na fila de destino.

## Solução Proposta

O InboxON recebe mensagens por webhook, identifica a intenção, atribui prioridade e encaminha cada mensagem à fila responsável. Cada gravação gera um comprovante cujo ID permite consultar o registro da mensagem. Um pedido de segunda via vai para o financeiro. Uma falha que interrompe vendas vai para a fila prioritária. Quando o motor de classificação está indisponível ou sua resposta é inválida, a mensagem segue para triagem manual.

### Arquitetura

```mermaid
flowchart LR
    Cliente -->|POST webhook| N8N[n8n]
    N8N -->|Classificar e registrar| API[FastAPI]
    API -->|Inferência local| Ollama[Ollama e Qwen3]
    API -->|Gravar e consultar| SQLite[(SQLite)]
```

A FastAPI valida a entrada e pede ao Ollama uma saída conforme JSON Schema. O Pydantic valida o retorno antes de aceitá-lo. O n8n decide a fila, solicita a gravação à API e devolve o recibo ao cliente. O Ollama roda dentro da rede do Compose, na mesma máquina, e o modo local dispensa chave de API externa.

## Tecnologias Utilizadas

| Camada | Stack |
| --- | --- |
| Serviço HTTP | Python 3.12, FastAPI, Uvicorn, Pydantic e HTTPX |
| Inferência local | Ollama 0.40.18 e Qwen3 1.7B (`qwen3:1.7b`), em CPU |
| Automação | n8n 2.49.6, com workflow versionado em JSON |
| Persistência | SQLite em modo WAL, com chave única por encaminhamento |
| Infraestrutura e testes | Docker Compose, `unittest` e teste de integração HTTP |

## Funcionamento do Sistema

O n8n recebe o corpo do webhook e chama a API de classificação. A API valida a mensagem, envia as instruções de classificação e o JSON Schema ao serviço local de inferência e valida a resposta. Com o resultado aceito, o n8n aplica as regras de fila, chama a API de gravação e devolve o comprovante. Quando a entrada é inválida, o fluxo responde `422` sem gravar um encaminhamento.

### Contrato HTTP

| Endpoint | Comportamento |
| --- | --- |
| `GET /health` | Indica que a API iniciou e informa o modo `demo` ou `ollama`. |
| `POST /classificacoes` | Recebe `{"mensagem":"..."}` e retorna `200` com ID, origem e classificação. |
| `POST /encaminhamentos` | Registra a mensagem e sua fila. Retorna `201` para uma nova gravação, `200` se o mesmo ID e conteúdo já estiverem registrados, ou `409` se o ID for reutilizado com outro conteúdo. |
| `GET /encaminhamentos?fila=financeiro&limite=20` | Lista os registros mais recentes da fila. O limite aceito é de 1 a 100. |
| `POST /webhook/classificar-mensagem` | Executa classificação, roteamento e gravação. Retorna `201` após persistir, `422` para entrada inválida ou `502` quando a integração com a API falha. |

A mensagem deve ter de 1 a 3.000 caracteres após a remoção de espaços nas extremidades. O contrato rejeita propriedades extras. A classificação contém `categoria`, `prioridade`, `resumo` e `setor_sugerido`. A origem distingue inferência (`ollama`), regras locais de demonstração (`demonstracao`) e triagem por indisponibilidade ou saída inválida (`fallback`).

### Ordem de roteamento

| Primeira condição atendida | Destino |
| --- | --- |
| Origem `fallback` | `triagem` |
| Prioridade `alta` | `prioritario` |
| Categoria `outro` | `triagem` |
| Demais classificações | Setor sugerido: `atendimento`, `comercial`, `financeiro`, `operacoes` ou `suporte` |

A proteção contra duplicidade vale para a gravação com o mesmo ID. Cada nova chamada ao webhook gera seu próprio ID. No Compose, a API e o editor do n8n escutam somente no loopback do host. O Ollama não publica porta no host. Use mensagens fictícias para demonstração, pois a fila e o histórico do n8n armazenam o texto original.

### Validação na VPS

Validação de 25/11/2026 em Docker Compose, com o workflow publicado e a API em modo `ollama`.

| Caso | Categoria | Fila | Resultado |
| --- | --- | --- | --- |
| Preço de um plano | `duvida` | `comercial` | `201`, `origem: ollama`, registro consultado |
| Segunda via de boleto | `solicitacao` | `financeiro` | `201`, `origem: ollama`, registro consultado |
| Sistema fora do ar com vendas interrompidas | `reclamacao` | `prioritario` | `201`, `origem: ollama`, registro consultado |
| Pedido fora do prazo | `reclamacao` | `operacoes` | `201`, `origem: ollama`, registro consultado |
| Saudação sem solicitação | `outro` | `triagem` | `201`, `origem: ollama`, registro consultado |
| Mensagem em branco | — | — | `422` |

A bateria levou **71,27 s**. O `docker compose stats` mediu **aproximadamente 3 GiB de RAM somados** logo após o teste: Ollama **2,607 GiB**, n8n **401,8 MiB** e API **38,27 MiB**. Esses valores descrevem a execução observada na VPS.

A [evidência em JSON da execução nº 10](docs/prints/execucao-10.json) reúne o pedido de segunda via, a classificação `solicitacao`, a prioridade `media`, a fila `financeiro` e o mesmo ID na gravação e na consulta.

### Documentação visual do fluxo n8n

1. **Fluxo completo.** O editor mostra os seis nós, o caminho que grava o encaminhamento e a saída direta para responder a erros.

   ![Fluxo completo no editor do n8n](docs/prints/01-fluxo-completo.png)

2. **Execução bem-sucedida.** O histórico mostra a execução nº 10 concluída, com o percurso até a resposta do webhook. [Ver a execução nº 10](docs/prints/02-execucao-10-sucesso.png)

3. **Configuração individual dos nós.** As capturas mostram os parâmetros usados para receber, classificar, decidir, encaminhar e responder.

   | Nó | Configuração registrada |
   | --- | --- |
   | Receber mensagem | Webhook `POST` e resposta delegada ao último nó. [Ver captura](docs/prints/03-01-webhook.png) |
   | Classificar na API | Requisição JSON à API e leitura do status HTTP. [Ver captura](docs/prints/03-02-classificar.png) |
   | Classificação recebida? | Verificação do status `200`, do ID e da classificação. [Ver captura](docs/prints/03-03-condicao.png) |
   | Definir fila | Seleção da fila por origem, prioridade, categoria e setor. [Ver captura](docs/prints/03-04-definir-fila.png) |
   | Registrar encaminhamento | Requisição `POST` para gravar o encaminhamento. [Ver captura](docs/prints/03-05-registrar.png) |
   | Responder webhook | Expressões que montam o corpo e o código HTTP. [Ver captura](docs/prints/03-06-responder.png) |

4. **Resultados por etapa.** A trilha da execução nº 10 acompanha a mensagem do boleto até a consulta ao registro persistido.

   | Etapa | Resultado registrado |
   | --- | --- |
   | Entrada | Mensagem recebida no webhook. [Ver captura](docs/prints/04-01-entrada.png) |
   | Classificação | HTTP `200`, `origem: ollama` e dados da classificação. [Ver captura](docs/prints/04-02-classificacao.png) |
   | Roteamento | Fila `financeiro` escolhida para o pedido. [Ver captura](docs/prints/04-03-fila.png) |
   | Gravação | HTTP `201`, ID do comprovante e data do registro. [Ver captura](docs/prints/04-04-gravacao.png) |
   | Resposta | Saída do nó de resposta com HTTP `201`. [Ver captura](docs/prints/04-05-resposta.png) |
   | Consulta | Mensagem original e mesmo ID na fila `financeiro`. [Ver captura](docs/prints/04-06-consulta.png) |

O [guia de evidências](docs/prints/README.md) detalha os campos de cada captura e como consultar o registro original.

## Como Executar

### Docker Compose

Requisitos: Docker Engine, Compose e acesso para baixar as imagens e o modelo. Execute na raiz do repositório. No PowerShell, use `Copy-Item .env.example .env` para copiar a configuração.

```bash
cp .env.example .env
docker compose --profile inferencia up -d --wait ollama
docker compose --profile inferencia exec -T ollama ollama pull qwen3:1.7b
```

No `.env`, defina `CLASSIFIER_MODE=ollama`. O modo padrão `demo` permite testar o fluxo sem carregar o modelo. O primeiro download do Qwen3 usa cerca de 1,4 GB de disco, além da imagem do Ollama.

```bash
docker compose --profile inferencia up -d --build --wait
docker compose --profile inferencia ps
```

1. Abra `http://localhost:5678` no host. Se estiver em uma VPS, use o túnel descrito no [guia operacional](docs/entrega.md#acesso-ao-n8n-na-vps).
2. Crie a conta local no primeiro acesso. Em um workflow vazio, escolha **Import from File** e selecione [`n8n/workflow-classificacao-mensagens.json`](n8n/workflow-classificacao-mensagens.json).
3. Salve e publique o workflow. O webhook publicado fica em `/webhook/classificar-mensagem`.

Em modo `demo`, basta `docker compose up -d --build --wait`. Para encerrar o ambiente, use `docker compose --profile inferencia down`. Esse comando preserva os volumes com o workflow, a fila e o modelo.

### API e testes de integração

```bash
curl -fsS http://127.0.0.1:8000/health

curl -i http://127.0.0.1:5678/webhook/classificar-mensagem \
  -H 'Content-Type: application/json' \
  --data '{"mensagem":"Podem emitir a segunda via do boleto?"}'

curl -fsS 'http://127.0.0.1:8000/encaminhamentos?fila=financeiro&limite=20'
python3 tests/smoke_n8n.py --modo ollama
```

O webhook deve devolver HTTP `201`, `origem: ollama` e `fila: financeiro`. Confirme o ID do comprovante na consulta à fila. Para testar com regras locais, execute `python3 tests/smoke_n8n.py` com a API em `demo`. O contrato HTTP pode ser consultado em `http://127.0.0.1:8000/docs`.

### API local sem Docker

Na raiz do projeto, instale as dependências em um ambiente virtual com Python 3.12. O comando abaixo inicia a API em modo `demo`, usando SQLite local.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000/docs` para exercitar a API. O Docker Compose prepara a rede para o workflow exportado, que chama a API pelo endereço `http://api:8000`.

Para rodar os testes unitários, use o mesmo ambiente virtual.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

No Windows, o executável equivalente é `.\.venv\Scripts\python.exe`. Consulte o [guia operacional](docs/entrega.md) para acesso à VPS, atualização e captura de evidências.
