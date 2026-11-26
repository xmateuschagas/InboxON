# Capturas do fluxo n8n

A execução nº 10 recebeu `Podem emitir a segunda via do boleto?`. O serviço registrou `origem: ollama`, categoria `solicitacao`, prioridade `media` e fila `financeiro`. O [JSON da execução](execucao-10.json) reúne a saída de cada etapa e o registro consultado na fila. Para acessar o editor e capturar as telas, siga o [guia operacional](../entrega.md#acesso-ao-n8n-na-vps).

No Windows, pressione **Win + Shift + S**, selecione a área do n8n e salve o recorte como PNG nesta pasta. Inclua o nome do workflow e os campos da evidência. Use mensagens fictícias e mantenha credenciais, barra de favoritos e dados pessoais fora do enquadramento.

## 1. Fluxo completo

A [captura do fluxo completo](01-fluxo-completo.png) mostra os seis nodes e as duas saídas do IF no **Editor**. O ramo verdadeiro prepara e registra o encaminhamento. O ramo falso segue direto para a resposta HTTP de erro.

## 2. Execução bem-sucedida

A [captura da execução nº 10](02-execucao-10-sucesso.png) mostra o status **Succeeded** e o trajeto até **Responder webhook**. A saída de **Registrar encaminhamento** contém o ID `4ba83d42-ffa6-47f8-81a8-54c38deae8ef`.

## 3. Configuração individual dos nodes

No **Editor**, abra cada node e capture a aba **Parameters**. Quando os campos estiverem abaixo da área visível, expanda as opções, reduza o zoom ou faça uma segunda imagem com o mesmo prefixo.

| Arquivo | Node | O que mostrar |
| --- | --- | --- |
| [03-01-webhook.png](03-01-webhook.png) | Receber mensagem | Método `POST`, path `classificar-mensagem` e resposta via **Respond to Webhook**. |
| [03-02-classificar.png](03-02-classificar.png) | Classificar na API | URL `/classificacoes`, corpo JSON a partir de `$json.body`, retorno com status e corpo, **Never Error** e timeout de 50.000 ms. |
| [03-03-condicao.png](03-03-condicao.png) | Classificação recebida? | Condição booleana que verifica o HTTP `200` e os campos `id` e `classificacao`. |
| [03-04-definir-fila.png](03-04-definir-fila.png) | Definir fila | Modo **JSON Output** e expressão que escolhe a fila por origem, prioridade, categoria e setor. |
| [03-05-registrar.png](03-05-registrar.png) | Registrar encaminhamento | URL `/encaminhamentos`, método `POST`, corpo construído pelo node anterior, retorno com status e corpo e timeout de 8.000 ms. |
| [03-06-responder.png](03-06-responder.png) | Responder webhook | Expressões do corpo JSON e do código de resposta, com repasse de `201`/`200`, entrada inválida `422` e erro de integração `502`. |

## 4. Resultados de cada etapa importante

Volte à execução bem-sucedida, abra os nodes correspondentes e exiba **Input** ou **Output** em JSON. Use o mesmo ID de classificação nos prints da chamada à API, da decisão e da gravação.

| Arquivo | O que deve aparecer |
| --- | --- |
| [04-01-entrada.png](04-01-entrada.png) | Saída de **Receber mensagem**, com `body.mensagem`. |
| [04-02-classificacao.png](04-02-classificacao.png) | Saída de **Classificar na API**, com `statusCode: 200`, `id`, `origem` e os quatro campos de `classificacao`. |
| [04-03-fila.png](04-03-fila.png) | Saída de **Definir fila**, com `fila: financeiro`, o mesmo ID e a mensagem original. |
| [04-04-gravacao.png](04-04-gravacao.png) | Saída de **Registrar encaminhamento**, com `statusCode: 201`, `fila`, `id` e `registrado_em`. |
| [04-05-resposta.png](04-05-resposta.png) | Saída de **Responder webhook** na execução nº 10, com `statusCode: 201`. |
| [04-06-consulta.png](04-06-consulta.png) | Resultado de `GET /encaminhamentos?fila=financeiro` com o mesmo ID e o texto armazenado. |

Para reencontrar o registro original na fila, mesmo depois de novas chamadas, execute na VPS:

```bash
curl -fsS 'http://127.0.0.1:8000/encaminhamentos?fila=financeiro&limite=100' \
  | python3 -c 'import json,sys; linhas=json.load(sys.stdin); id="4ba83d42-ffa6-47f8-81a8-54c38deae8ef"; print(json.dumps(next(linha for linha in linhas if linha["id"] == id), ensure_ascii=False, indent=2))'
```

Confira se o texto dos PNGs está legível antes de adicioná-los ao repositório.
