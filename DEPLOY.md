# GitHub + Render Free — versão 1.6.0

O pacote está configurado para um **Python Web Service no plano Free do Render**,
sem disco pago, com Firebase Spark opcional. O GitHub guarda o código; o Render
executa o aplicativo. GitHub Pages não executa este servidor Python/Flet.

## Como os dados são guardados no Free

**Com Firebase:** siga [FIREBASE.md](FIREBASE.md) para criar o projeto Spark,
configurar a credencial no Render e ativar `RSO_BACKEND=firebase`. Rascunhos e fotos
confirmados como Salvo no Firebase sobrevivem à perda do disco do Render.
O restante desta seção descreve o modo **local**, padrão antes dessa configuração.

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
   Em **RSO_BACKEND**, informe `local` para começar, ou `firebase` somente depois
   de configurar projeto e credencial conforme FIREBASE.md.
5. Confirme que aparece **Free**, sem disco persistente, e conclua a criação.
6. Aguarde o estado **Live**. Abra a URL HTTPS `https://...onrender.com`.
7. Informe `admin` e sua senha no diálogo do navegador.

O `render.yaml` contém `plan: free`, não declara `disk` e não cria banco de dados.
A chave de upload é gerada pelo Render. As quatro abas iniciais vêm com os dados cadastrais dos modelos; os campos semanais começam vazios;
os relatórios históricos do pacote não são carregados automaticamente.

**Atualizações automáticas estão desligadas** (`autoDeployTrigger: "off"`).
Antes de cada atualização, baixe o backup. Depois faça push, aguarde os testes
em Actions e use **Manual Deploy → Deploy latest commit** no Render. Ao terminar,
restaure o ZIP no modo local. Com Firebase ativo, os dados confirmados são recuperados
automaticamente; não restaure o ZIP a cada deploy para evitar cópias duplicadas.
Isso não impede suspensões e reinícios realizados pelo próprio Render.

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
| `RSO_BACKEND` | `local`, ou `firebase` após configurar FIREBASE.md |
| `TZ` | `America/Fortaleza` |

O Render fornece `PORT`. Para gerar a chave no computador:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Cole o resultado apenas em `FLET_SECRET_KEY` no painel Environment. Não grave
senhas ou chaves no repositório. `RSO_STORAGE_MODE` controla o aviso visual; não
transforma armazenamento temporário em permanente.

## Usar backup e restauração

1. Aguarde o fim dos uploads e a indicação de salvamento no formulário:
   **Salvo no Firebase** com nuvem ativa, ou **Salvo temporariamente** no modo local.
2. Abra **Backup e restauração** no topo do aplicativo. Também é possível abrir
   `/backup` diretamente na URL do serviço, usando a mesma senha.
3. Clique **Baixar backup ZIP** e confirme o arquivo na pasta de downloads.
4. Para recuperar, selecione o ZIP em **Restaurar backup** e clique **Restaurar obras**.
5. Após a mensagem de sucesso, feche janelas antigas e abra/recarregue o aplicativo.
   As obras reaparecem em novas abas com o sufixo **(restaurada)**.

O ZIP contém os rascunhos de todas as obras, inclusive incompletos, e suas fotos
atuais com seus títulos de atividade. A restauração preserva as obras existentes e cria cópias;
restaurar o mesmo ZIP novamente cria outras cópias. Fotos removidas, versões JSON
anteriores e PDFs/XLSX já exportados não entram no backup. Os relatórios podem ser
regenerados. As fotos são gerais da semana, com a atividade acima das imagens, sem dia/data.

O backup tem limite de **100 MB**; a restauração também limita o conteúdo
expandido a 200 MB. Fotos exportadas pelo aplicativo já são reduzidas para até
2800 pixels no maior lado. Guarde o ZIP em local privado: ele contém os dados das obras.

## Acesso e limites

- A interface, os uploads, os downloads e os backups exigem senha. `/healthz` é
  público e retorna apenas `{"status":"ok"}`. Use a URL HTTPS do Render.
- Use **uma janela de edição por vez** e **um worker**. Não há contas individuais,
  permissões por obra ou sincronização entre editores; todos com a senha veem todas as obras.
- O navegador precisa de conexão. No modo local, **Salvar Rascunho** salva somente no
  servidor temporário. Com Firebase, o botão também antecipa a sincronização;
  aguarde a confirmação de dados e fotos. O backup ZIP continua disponível.
- Para trabalhar offline com dados locais persistentes, use `python main.py` no computador.
  Instalações configuradas com o mesmo projeto e namespace Firebase recuperam os
  mesmos relatórios ao abrir. Evite editar simultaneamente o mesmo relatório.
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
| Exportação reclama das fotos | Verifique se os arquivos de imagem ainda existem; reimporte os ausentes. |
| Upload mostra `Stream has already been listened to` ou trava ao enviar várias fotos | Atualize para 1.6.0, recarregue a página e use **Adicionar fotos** para selecionar novamente os arquivos que falharam. |
| Firebase não conecta ou salvamento fica pendente | Siga FIREBASE.md; confira projeto, banco (default), credencial, IAM e cotas. O erro não ativa faturamento nem troca silenciosamente para armazenamento local. |

Referências: [Free](https://render.com/docs/free),
[Blueprint](https://render.com/docs/blueprint-spec),
[Python](https://render.com/docs/python-version) e
[FastAPI](https://render.com/docs/deploy-fastapi).

## Atualizar para dados fixos e fotos semanais (1.4)

Baixe o backup antes de qualquer deploy no Free. Substitua os arquivos do repositório
pelos desta versão, mantendo **as pastas completas** `rso/`, `assets/`, `tools/` e
`tests/` ao lado de `web.py`. Envie também `tests/`: as regras antigas foram substituídas por
`tests/test_weekly_photos.py`. Depois use **Manual Deploy**.

Se aparecer `ModuleNotFoundError: No module named 'rso'`, a pasta `rso/` não foi enviada
para o mesmo nível de `web.py`. Não mova os arquivos internos dela para a raiz.
Os clientes/responsáveis/CREA/ART/alvarás são fixos por obra. Endereços e cliente do
Átrio permanecem editáveis conforme autorizado. Restaure seu ZIP após o deploy;
os campos semanais são preservados e o cadastro reconhecido é atualizado pelo modelo.
