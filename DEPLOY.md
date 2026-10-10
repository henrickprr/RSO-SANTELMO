# GitHub + Render Free — versão 1.3

O pacote está configurado para um **Python Web Service no plano Free do Render**,
sem disco pago e sem banco de dados externo. O GitHub guarda o código; o Render
executa o aplicativo. GitHub Pages não executa este servidor Python/Flet.

## Como os dados são guardados no Free

O aplicativo salva rascunhos e fotos em `/tmp/rso-data`. **Essa pasta é temporária**:
seu conteúdo se perde quando o Render suspende, reinicia ou reimplanta o serviço.
O Free pode suspender o serviço após 15 minutos sem tráfego; a próxima abertura
pode levar aproximadamente um minuto. Não conte com a janela aberta para preservar dados.

Use **Backup e restauração → Baixar backup ZIP** durante o trabalho e antes de sair.
Confirme que o arquivo chegou ao seu computador. Depois de uma perda dos dados
locais, envie esse ZIP em **Restaurar obras**. Apenas o conteúdo do último backup
baixado poderá ser recuperado. O backup é manual; não há sincronização automática
com o GitHub, armazenamento em nuvem permanente ou cópia automática no navegador.

## 1. Enviar ao GitHub

1. Extraia o ZIP. A pasta correta contém `render.yaml`, `web.py` e `README.md`.
2. Crie um repositório **privado**, como `rso-santelmo`. O pacote inclui os PDFs e
   fotos reais de referência em `references/` e `examples/`.
3. Envie o **conteúdo extraído**, incluindo `.github`, `.python-version` e `.gitignore`.
   Deixe `render.yaml` na raiz. Não envie apenas o ZIP.
4. Use a branch `main`. O workflow **Validar RSO**, em **Actions**, verifica o código.

Com Git instalado, dentro da pasta extraída, substitua SEU-USUARIO:

```bash
git init
git branch -M main
git add .
git commit -m "RSO Santelmo para Render Free"
git remote add origin https://github.com/SEU-USUARIO/rso-santelmo.git
git push -u origin main
```

Esses comandos pressupõem um repositório remoto vazio. Para atualizar um existente,
copie os arquivos para seu clone e faça commit normalmente. GitHub Desktop também
pode ser usado. Não envie `.env`, senhas, rascunhos em uso ou backups ao GitHub.
O `.gitignore` exclui `.env`, ambientes virtuais, ZIPs e as pastas usuais de dados.

## 2. Criar no Render usando Blueprint

1. Em [dashboard.render.com](https://dashboard.render.com/), escolha **New → Blueprint**.
2. Conecte o GitHub e autorize o acesso ao repositório privado.
3. Selecione a branch `main` e `render.yaml` na raiz.
4. Cadastre **RSO_PASSWORD**, com pelo menos 12 caracteres. O usuário inicial é **admin**.
5. Confirme que aparece **Free**, sem disco persistente, e conclua a criação.
6. Aguarde o estado **Live**. Abra a URL HTTPS `https://...onrender.com`.
7. Informe `admin` e sua senha no diálogo do navegador.

O `render.yaml` contém `plan: free`, não declara `disk` e não cria banco de dados.
A chave de upload é gerada pelo Render. As quatro abas iniciais ficam vazias;
os relatórios históricos do pacote não são carregados automaticamente.

**Atualizações automáticas estão desligadas** (`autoDeployTrigger: "off"`).
Antes de cada atualização, baixe o backup. Depois faça push, aguarde os testes
em Actions e use **Manual Deploy → Deploy latest commit** no Render. Ao terminar,
restaure o ZIP. Isso não impede suspensões e reinícios realizados pelo próprio Render.

### Se você já criou um serviço pago

Alterar o ZIP ou o repositório não cancela nem modifica cobranças de um serviço
existente. Um serviço com disco anexado não pode simplesmente usar esse disco no Free.

- Preserve os dados do serviço antigo antes de qualquer mudança. Para usar os novos
  botões de backup nele, publique esta versão mantendo sua pasta de dados atual
  (`/var/data/rso` no Blueprint anterior), baixe o ZIP e confirme o download.
- Crie um **novo Web Service Free** pelo procedimento manual abaixo, com nome diferente,
  por exemplo `rso-santelmo-free`. Não anexe disco.
- Restaure o backup no serviço novo e confira rascunhos, legendas e fotos.
- Só depois gerencie o encerramento dos recursos pagos antigos no painel do Render.

## Alternativa: criar um Web Service manualmente

| Campo | Valor |
|---|---|
| Language / Runtime | Python 3 |
| Branch | `main` |
| Root Directory | vazio, se o código está na raiz |
| Instance Type | **Free** |
| Build Command | `pip install -r requirements-web.txt` |
| Start Command | `python -m uvicorn web:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers` |
| Health Check Path | `/healthz` |
| Auto-Deploy | **Off** |
| Disk | **Não adicionar** |

A versão do Python vem de `.python-version` (**3.12.11**). Cadastre as variáveis:

| Variável | Valor |
|---|---|
| `RSO_USERNAME` | `admin` ou nome ASCII sem `:` |
| `RSO_PASSWORD` | Sua senha, com pelo menos 12 caracteres |
| `FLET_SECRET_KEY` | Chave aleatória, com pelo menos 32 caracteres |
| `RSO_DATA_DIR` | `/tmp/rso-data` |
| `RSO_STORAGE_MODE` | `ephemeral` |
| `TZ` | `America/Fortaleza` |

O Render fornece `PORT`. Para gerar a chave no computador:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Cole o resultado apenas em `FLET_SECRET_KEY` no painel Environment. Não grave
senhas ou chaves no repositório. `RSO_STORAGE_MODE` controla o aviso visual; não
transforma armazenamento temporário em permanente.

## Usar backup e restauração

1. Aguarde o fim dos uploads e a indicação **Salvo temporariamente** no formulário.
2. Abra **Backup e restauração** no topo do aplicativo. Também é possível abrir
   `/backup` diretamente na URL do serviço, usando a mesma senha.
3. Clique **Baixar backup ZIP** e confirme o arquivo na pasta de downloads.
4. Para recuperar, selecione o ZIP em **Restaurar backup** e clique **Restaurar obras**.
5. Após a mensagem de sucesso, feche janelas antigas e abra/recarregue o aplicativo.
   As obras reaparecem em novas abas com o sufixo **(restaurada)**.

O ZIP contém os rascunhos de todas as obras, inclusive incompletos, e suas fotos
atuais com dias e legendas. A restauração preserva as obras existentes e cria cópias;
restaurar o mesmo ZIP novamente cria outras cópias. Fotos removidas, versões JSON
anteriores e PDFs/XLSX já exportados não entram no backup. Os relatórios podem ser
regenerados. A exportação continua exigindo **2 ou 4 fotos por dia útil do período**.

O backup tem limite de **100 MB**; a restauração também limita o conteúdo
expandido a 200 MB. Fotos exportadas pelo aplicativo já são reduzidas para até
2800 pixels no maior lado. Guarde o ZIP em local privado: ele contém os dados das obras.

## Acesso e limites

- A interface, os uploads, os downloads e os backups exigem senha. `/healthz` é
  público e retorna apenas `{"status":"ok"}`. Use a URL HTTPS do Render.
- Use **uma janela de edição por vez** e **um worker**. Não há contas individuais,
  permissões por obra ou sincronização entre editores; todos com a senha veem todas as obras.
- O navegador precisa de conexão. No Free, **Salvar Rascunho** salva somente no servidor
  temporário; use o backup ZIP para guardar uma cópia fora dele.
- Para trabalhar offline com dados locais persistentes, use `python main.py` no computador.
  As instalações local e remota não sincronizam automaticamente.
- O Free está sujeito às cotas do Render (incluindo horas compartilhadas pelo workspace,
  tráfego e builds). Consulte o painel e a [documentação do Free](https://render.com/docs/free).
  Esta configuração não adiciona serviços pagos nem mecanismos para evitar a suspensão.
- Para trocar a senha, altere `RSO_PASSWORD` e reinicie o serviço. **Baixe o backup antes.**
  O navegador pode memorizar HTTP Basic até ser fechado; use janela privativa em computador compartilhado.

## Testar no computador

Crie e ative um ambiente virtual e instale:

```bash
python -m pip install -r requirements-web.txt
```

Copie `.env.example` para `.env`, preencha senha e chave, e mantenha
`RSO_DATA_DIR=./dados-rso` e `RSO_STORAGE_MODE=local`. Execute:

```bash
python -m uvicorn web:create_app --factory --env-file .env --host 127.0.0.1 --port 8550 --workers 1
```

Abra `http://127.0.0.1:8550`. Para ver o aviso de armazenamento temporário, troque
`RSO_STORAGE_MODE` por `ephemeral` e reinicie. O `.env` só é lido com `--env-file`;
no Render, use Environment. Em teste local, a pasta persiste; isso não simula a
eliminação do sistema de arquivos que o Render Free realiza.

## Problemas comuns

| Sintoma | Como resolver |
|---|---|
| Build não acha `requirements-web.txt` | Confira a raiz do repositório e Root Directory. |
| Log pede senha/chave | Cadastre as variáveis com os tamanhos mínimos. |
| Render demora a abrir | Aguarde a retomada do Free e recarregue se necessário. |
| Dados sumiram após suspensão/deploy | Restaure o último ZIP baixado. Sem backup, os dados não são recuperáveis. |
| Backup não baixa | Aguarde uploads; confira fotos ausentes, integridade dos rascunhos e limite de 100 MB. |
| ZIP não é aceito | Use o ZIP de **Baixar backup**, não o ZIP do código-fonte ou os PDFs. |
| PDF/XLSX não abre | Permita pop-ups para a URL do aplicativo. |
| Exportação reclama das fotos | Complete cada dia do período com exatamente 2 ou 4 fotos. |

Referências: [Free](https://render.com/docs/free),
[Blueprint](https://render.com/docs/blueprint-spec),
[Python](https://render.com/docs/python-version) e
[FastAPI](https://render.com/docs/deploy-fastapi).
