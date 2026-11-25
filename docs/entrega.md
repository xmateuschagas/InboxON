# Guia de entrega e operação

## Acesso ao n8n na VPS

No PowerShell do Windows, execute o túnel com o alias da VPS e deixe a janela aberta. Use uma janela separada para os outros comandos.

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:15678:127.0.0.1:5678 servidor168
```

Abra `http://localhost:15678`. Se a sessão tiver expirado, entre com a conta local do n8n. Digite a senha diretamente na página de login. No workflow **KODIE | Classificação de mensagens**, abra **Execuções** e selecione a **nº 10**. Confira o status **Success** e a mensagem sobre a segunda via do boleto. A execução começou às **14:10:00** no horário de Brasília em 25/11/2026.

Use o [índice de capturas](prints/README.md) para salvar os PNGs na pasta `docs/prints/` do checkout local. A [evidência JSON](prints/execucao-10.json) foi extraída do histórico de execução e conferida com o registro persistido na fila financeira. Ela permite conferir o caso mesmo se a política de retenção do n8n já tiver removido a entrada do editor.

Se a execução nº 10 tiver expirado, gere uma nova execução com a mesma mensagem. Na VPS, rode:

```bash
curl -i http://127.0.0.1:5678/webhook/classificar-mensagem \
  -H 'Content-Type: application/json' \
  --data '{"mensagem":"Podem emitir a segunda via do boleto?"}'
```

Confirme `201`, `origem: ollama` e `fila: financeiro`. No editor, selecione a nova execução e use o ID do novo recibo para conferir as telas. A evidência da execução nº 10 permanece registrada no JSON.

## Sincronizar código sem arquivos do ambiente

A publicação usa um pacote de fonte separado do diretório de execução. O ZIP inclui a API, o workflow JSON, o Compose, os testes, o README e as evidências. A lista de exclusão cobre `.env`, bancos locais, chaves, logs, backups, caches e arquivos temporários. O `.env.example` tem apenas parâmetros de exemplo.

Para transferir o snapshot da VPS, rode no PowerShell:

```powershell
$zip = Join-Path $env:USERPROFILE 'Downloads\kodie-classificacao-mensagens.zip'
scp servidor168:/root/kodie-portfolio/kodie-classificacao-mensagens.zip $zip
if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar o pacote da VPS.' }
$destino = Join-Path $env:USERPROFILE ('Documents\kodie-portfolio-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
Expand-Archive -LiteralPath $zip -DestinationPath $destino
Set-Location (Join-Path $destino 'kodie-classificacao-mensagens')
Get-ChildItem -Force
```

Para trabalhar na versão publicada, clone o repositório. Assim, o próximo commit mantém o histórico existente.

```powershell
git clone https://github.com/xmateuschagas/kodie-classificacao-mensagens.git
Set-Location kodie-classificacao-mensagens
```

## Publicação no GitHub

### Primeira publicação

Execute a partir do diretório que contém o `README.md`. Se a autenticação estiver expirada, use `gh auth login --hostname github.com --git-protocol https --web` e conclua o login no navegador.

```powershell
gh auth status
gh auth setup-git
git init -b main
git add -- .dockerignore .env.example .gitignore app docs n8n tests Dockerfile docker-compose.yml requirements.txt README.md
git diff --cached --check
git diff --cached --name-only
```

Confira a lista. O `.env`, o banco SQLite, as credenciais do n8n e arquivos temporários devem ficar fora do commit. Se o repositório ainda não existir, rode:

```powershell
git commit -m "Publica classificador e roteamento de mensagens"
gh repo create xmateuschagas/kodie-classificacao-mensagens --public --source=. --remote=origin --push
gh repo view xmateuschagas/kodie-classificacao-mensagens --json url,visibility,defaultBranchRef
```

### Acrescentar capturas após a publicação

No checkout do repositório, copie os PNGs para `docs/prints/`, confira o conteúdo das telas e rode:

```powershell
git add -- 'docs/prints/*.png'
git diff --cached --check
git diff --cached --name-only
git commit -m "Adiciona capturas da execução e configurações do n8n"
git push origin main
```

Para repetir a verificação da inferência local na VPS, rode `python3 tests/smoke_n8n.py --modo ollama`. Os testes da API podem ser executados com `python3 -m unittest discover -s tests -v` em um ambiente com as dependências do projeto.
