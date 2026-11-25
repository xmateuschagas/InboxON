# Guia operacional do InboxON

## Acesso ao n8n na VPS

Abra um túnel SSH e mantenha o terminal aberto. Substitua `usuario@host` pelos dados de acesso da VPS.

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:15678:127.0.0.1:5678 usuario@host
```

Acesse `http://localhost:15678` e entre na conta local do n8n. No editor, localize o fluxo cujo webhook usa o caminho `classificar-mensagem` e abra a aba **Execuções**. A execução **nº 10**, quando ainda disponível, mostra o processamento do pedido de segunda via em 25/11/2026, às 14:10 no horário de Brasília.

A [evidência em JSON](prints/execucao-10.json) documenta as etapas dessa execução e o registro consultado na fila financeira. Para registrar uma nova execução, rode este comando na VPS:

```bash
curl -i http://127.0.0.1:5678/webhook/classificar-mensagem \
  -H 'Content-Type: application/json' \
  --data '{"mensagem":"Podem emitir a segunda via do boleto?"}'
```

Com o serviço de inferência local ativo, confirme `201`, `origem: ollama` e `fila: financeiro`. Use o ID do comprovante para correlacionar a execução com a consulta à fila. O [índice de capturas](prints/README.md) lista as telas que documentam o fluxo.

## Atualizar uma instalação existente

Execute a atualização com o mesmo nome de projeto do Docker Compose usado na implantação atual. Se mover o checkout para outra pasta, confirme o nome em `docker compose ls` e informe-o com `docker compose -p NOME_ATUAL` para reutilizar os volumes existentes da API, do n8n e do Ollama.

Reconstrua a imagem da API após atualizar o código. Em uma instalação com o perfil `inferencia` ativo, execute:

```bash
docker compose --profile inferencia up -d --build --wait
```

Para aplicar o nome **InboxON | Classificação de mensagens** a um fluxo já publicado, renomeie o fluxo existente no editor do n8n. A reimportação do JSON pode criar outro fluxo com o mesmo caminho de webhook.

## Validar após a atualização

```bash
python3 tests/smoke_n8n.py --modo ollama
python3 -m unittest discover -s tests -v
```

O primeiro comando verifica o webhook publicado em modo `ollama` e consulta os registros nas filas. O segundo usa um ambiente Python com as dependências do projeto instaladas.
