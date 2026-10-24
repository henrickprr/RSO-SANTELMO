# Firebase gratuito — salvamento automático do RSO 1.8.0

Os cadastros feitos em **Adicionar obra** acompanham os relatórios sincronizados.
Depois de recuperar os dados da nuvem, a obra volta a aparecer em **Novo relatório**.
A configuração e as regras são as mesmas da versão 1.6.0.

Correções confirmadas com **Fixar Informações** e exclusões ficam em
`rso_workspaces/{namespace}/projects/{obra}`. A coleção é criada pelo app; não precisa
ser criada manualmente. São transações com controle de revisão: uma correção antiga
não substitui outra mais recente. A exclusão deixa um pequeno marcador permanente
que bloqueia gravações de sessões antigas e impede a recriação da obra ao reiniciar.
Os documentos dos relatórios excluídos são apagados; se a limpeza for interrompida,
a próxima abertura tenta novamente e a obra continua fora da interface.

Os blocos de imagens por hash podem ser compartilhados entre relatórios e são
mantidos no Firestore para não danificar outras cópias. Excluir uma obra remove suas
referências, mas não libera automaticamente esse espaço de imagens na cota gratuita.
As fotos locais sem referências em outros relatórios são removidas.
Uma restauração explícita de backup recupera a obra excluída com uma nova identidade.

Use **Render Free + Firebase Spark**, sem cadastrar faturamento. Esta versão usa
somente **Cloud Firestore Standard, banco `(default)`**. Não crie Cloud Storage,
Cloud Functions nem um banco Enterprise. O código não contrata serviços ou altera planos.

## Como será o trabalho na semana

1. Na segunda, abra a obra, confira o período da semana, escreva os serviços e envie fotos.
2. As alterações recebidas ficam no cache local imediatamente. Depois de uma pausa
   de 1,5 segundo na digitação, a sincronização envia dados e fotos ao Firebase.
   Digitação contínua é enviada em intervalos de até 8 segundos, se a rede permitir.
3. Antes de fechar, aguarde **Salvo no Firebase • dados e fotos**. Não é preciso
   clicar em Salvar Rascunho; esse botão antecipa uma tentativa de sincronização.
4. Nos dias seguintes, abra o mesmo relatório. Os registros anteriores são recuperados;
   preencha os serviços do dia e acrescente as fotos que desejar.
5. Na sexta, exporte PDF ou XLSX. Na semana seguinte, use **Novo relatório** para
   preservar o histórico da semana anterior.

As fotos continuam gerais da semana, com o nome da atividade acima das imagens,
sem dia/data na impressão. O PDF mantém sua paginação e o XLSX continua em uma aba.

## 1. Criar o projeto e o banco

1. Entre em <https://console.firebase.google.com/> e escolha **Criar projeto**.
2. Dê um nome, por exemplo `rso-santelmo`. Analytics é opcional e não é usado pelo app.
3. Confirme o plano **Spark**, sem conta de faturamento vinculada.
4. Em **Build → Firestore Database → Criar banco de dados**, escolha a edição
   **Standard**, ID **`(default)`**, uma região disponível e **modo de produção**.
   A região não pode ser alterada posteriormente. Este app não exige região específica.
5. Em **Configurações do projeto → Geral**, copie o **ID do projeto**. Ele não é
   o nome de exibição nem a chave de API web.

## 2. Proteger o acesso ao banco

Na aba **Regras** do Firestore, publique o conteúdo de `firestore.rules` deste pacote:

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

O acesso do navegador fica bloqueado. O aplicativo acessa o banco exclusivamente
pelo servidor Python, com a conta de serviço e permissões IAM. O login do aplicativo
continua sendo o usuário/senha do Render; as obras são compartilhadas pelos usuários
que conhecem esse acesso. Não é um sistema de contas individuais por cliente.

Para não indexar fotos/textos que não são pesquisados, em **Índices → Campo único →
Adicionar isenção**, desative os índices ascendente, descendente e de array destes campos:

| Grupo de coleções | Campo |
|---|---|
| `chunks` | `data` |
| `reports` | `payload` |
| `reports` | `media` |

O arquivo `firestore.indexes.json` contém as mesmas isenções. Para quem usa Firebase
CLI, as regras e índices podem ser publicados com
`firebase deploy --only firestore:rules,firestore:indexes --project SEU-ID`.
Confira o projeto selecionado antes de publicar regras em um banco já utilizado por outro app.

## 3. Criar a credencial do servidor

1. No [Google Cloud Console](https://console.cloud.google.com/), selecione o mesmo projeto.
2. Em **IAM e administrador → Contas de serviço**, crie uma conta, por exemplo `rso-render`.
3. Conceda o papel **Cloud Datastore User** (`roles/datastore.user`). Ele permite
   ler/gravar documentos do Firestore sem tornar a conta administradora do projeto.
4. Abra a conta criada → **Chaves → Adicionar chave → Criar nova chave → JSON**.
5. Guarde o JSON no seu computador. **Não envie esse arquivo ao GitHub ou ao chat.**
   Ele será inserido somente na área de segredos do Render.

Não use a configuração JavaScript `apiKey/authDomain`: ela não substitui a conta
de serviço utilizada por este aplicativo Python.

## 4. Configurar no Render

Antes de atualizar o código, baixe um backup do aplicativo atual. Envie o pacote
completo ao GitHub, preservando `rso/`, `assets/` e os arquivos de dependências.

No serviço existente do Render, entre em **Environment → Secret Files → Add Secret File**:

- Filename: `firebase-service-account.json`.
- Contents: conteúdo completo do JSON da conta de serviço.

Adicione estas variáveis em **Environment**:

| Nome | Valor |
|---|---|
| `RSO_BACKEND` | `firebase` |
| `FIREBASE_PROJECT_ID` | ID real do projeto criado |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/etc/secrets/firebase-service-account.json` |
| `RSO_FIREBASE_NAMESPACE` | `santelmo` |
| `FIREBASE_DATABASE_ID` | `(default)` |

Mantenha `RSO_DATA_DIR=/tmp/rso-data`, `RSO_STORAGE_MODE=ephemeral`, o serviço **Free**,
as credenciais de acesso do app e o comando de inicialização atual. O Build Command
continua **`pip install -r requirements-web.txt`**. As dependências Firebase já estão incluídas.

Alternativa ao Secret File: configure `FIREBASE_SERVICE_ACCOUNT_JSON` com o JSON
completo como variável secreta no Render. Use apenas uma das duas formas.

Faça **Manual Deploy → Deploy latest commit** e recarregue o aplicativo. Se o Render
pedir pagamento para outra funcionalidade, não é necessário contratá-la para este pacote.
Um erro de configuração não faz o app voltar silenciosamente ao armazenamento local.

## 5. Recuperar os relatórios existentes e conferir

1. Depois do deploy, restaure o ZIP em **Backup e restauração** se os arquivos locais
   tiverem sido apagados. A restauração preserva os dados criando novas abas.
2. Reabra o aplicativo e aguarde **Salvo no Firebase** nas abas restauradas.
3. Escreva um pequeno serviço e envie uma foto de teste. Aguarde a mesma confirmação.
4. Reabra a página e confira texto, legenda e foto. Em Firestore → Dados, aparecerá
   `rso_workspaces → santelmo → reports` e `photos`.
5. Só depois de confirmar, faça um novo deploy ou reinício no Render e verifique a recuperação.
   As fotos são baixadas novamente para o cache quando necessário.

Rascunhos que ainda estiverem no disco local são incluídos automaticamente na fila
ao abrir o aplicativo. O ZIP de backup continua disponível como cópia independente.
Não restaure o mesmo ZIP repetidamente: cada restauração cria novos relatórios.

## Limites do gratuito e falhas de conexão

Segundo as [cotas oficiais do Firestore](https://firebase.google.com/docs/firestore/quotas):

- 1 GiB de dados armazenados, incluindo documentos, metadados e índices.
- 50.000 leituras e 20.000 gravações de documentos por dia.
- 10 GiB de transferência de saída por mês.
- Uma base com cota gratuita por projeto; use a Standard `(default)`.

Fotos normalmente seriam armazenadas no Cloud Storage, mas ele
[exige Blaze](https://firebase.google.com/docs/storage/faqs-storage-changes-announced-sept-2024).
Para manter **sem faturamento**, esta versão guarda o JPEG normalizado no próprio
Firestore, em partes binárias de até 700 KiB. Não há corte adicional de resolução:
é a mesma imagem de até 2800 px utilizada no PDF/XLSX. Cada foto consome várias
operações conforme seu tamanho; imagens iguais reutilizam o mesmo conteúdo.
É uma solução para volume moderado, não armazenamento ilimitado de fotografias.

O aplicativo não habilita faturamento nem renova cotas. Se o Firebase negar uma
gravação, aparece **salvamento pendente**; há nova tentativa após 30 segundos, ou
5 minutos quando a API informa cota excedida. Salvar Rascunho antecipa a tentativa.
Consulte o painel de uso para acompanhar a capacidade restante.

Remover uma foto do relatório não apaga automaticamente suas partes no banco,
preservando outras referências e a recuperação. Arquivos órfãos de um envio
interrompido também podem ocupar espaço. Para limpeza/arquivamento, faça backup
e revise os documentos e suas subcoleções antes de excluir dados no console.

**No Render Free, pendências ainda não confirmadas podem ser perdidas se o servidor
reiniciar.** A fila local resiste a reinício do processo somente enquanto o disco
continuar disponível. O navegador precisa de internet para entregar os eventos
ao servidor Flet; esta versão não promete edição offline no navegador.

Use uma janela de edição por relatório. Edições concorrentes são detectadas para
não substituir silenciosamente outra versão. **Guardar como cópia** preserva a
edição em uma nova aba; depois reabra o aplicativo para atualizar a aba original.
Não há atualização colaborativa em tempo real entre formulários já abertos.

## Estrutura e testes

`rso/firebase_backend.py` contém o acesso ao Firestore; `rso/cloud_repository.py`
contém cache, fila, debounce, retries e proteção contra versões antigas. Credenciais
nunca entram no JSON de rascunho, no backup, no PDF/XLSX ou nos arquivos públicos.

Para usar Firebase também no desktop, instale `requirements-firebase.txt` e configure
as mesmas variáveis no ambiente, apontando a credencial para um arquivo local protegido.

Os testes comuns usam um backend controlado para simular falhas. Os testes opcionais
de integração usam o emulador oficial, sem conta e sem cobrança:

```bash
npx firebase-tools emulators:start --only firestore --project demo-rso-santelmo
# Em outro terminal, Linux/macOS:
FIRESTORE_EMULATOR_HOST=127.0.0.1:8787 python -m pytest tests/test_firebase_emulator.py -q
```

Não defina `FIRESTORE_EMULATOR_HOST` no Render. O emulador não substitui a conferência
final de IAM, regras, credenciais e cotas no seu projeto real.
