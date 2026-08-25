# 📦 EstoqueApp — Tutorial de Instalação

## O que é esse sistema?

Sistema de gerenciamento de estoque com:
- Cadastro de produtos com categorias
- Controle de entradas, saídas e ajustes
- Dashboard com alertas de estoque mínimo
- Banco de dados local (SQLite — sem precisar instalar servidor)

---

## Requisitos

| Ferramenta | Versão mínima | Para que serve |
|---|---|---|
| Python | 3.9+ | Rodar o servidor |
| pip | qualquer | Instalar dependências |

---

## Passo a Passo

### 1. Instalar o Python

**Windows:**
1. Acesse https://www.python.org/downloads/
2. Baixe o instalador (Windows x64)
3. **Importante:** marque "Add Python to PATH" antes de instalar
4. Clique em "Install Now"
5. Teste no terminal: `python --version`

**macOS:**
```bash
# Opção 1 — Homebrew (recomendado)
brew install python

# Opção 2 — baixar o instalador em python.org
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3 python3-pip -y
```

---

### 2. Baixar os arquivos do projeto

Coloque todos os arquivos em uma pasta, por exemplo `C:\EstoqueApp` (Windows) ou `~/EstoqueApp` (Mac/Linux).

A estrutura deve ser:
```
EstoqueApp/
├── app.py
├── requirements.txt
└── templates/
    └── index.html
```

---

### 3. Criar ambiente virtual (recomendado)

Um ambiente virtual isola as dependências do projeto para não conflitar com outros programas Python.

**Windows:**
```cmd
cd C:\EstoqueApp
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
cd ~/EstoqueApp
python3 -m venv venv
source venv/bin/activate
```

> Você saberá que o ambiente está ativo quando aparecer `(venv)` no início da linha do terminal.

---

### 4. Instalar as dependências

Com o ambiente virtual ativo, rode:

```bash
pip install -r requirements.txt
```

Isso instala apenas o **Flask** (framework web leve para Python).

---

### 5. Iniciar o servidor

```bash
python app.py
```

Você verá a mensagem:
```
✅  Banco de dados inicializado.
🚀  Servidor rodando em http://127.0.0.1:5000
```

---

### 6. Acessar o sistema

Abra o navegador e acesse:

```
http://127.0.0.1:5000
```

O sistema estará funcionando! 🎉

---

## Sobre o Banco de Dados (SQLite)

O banco de dados é criado automaticamente como um arquivo chamado **`estoque.db`** na mesma pasta do projeto.

**Vantagens do SQLite para uso local:**
- Não precisa instalar nenhum servidor de banco de dados
- O arquivo `.db` pode ser copiado/backup facilmente
- Funciona sem internet
- Suporta bem até ~100.000 produtos

**Para fazer backup:** basta copiar o arquivo `estoque.db`.

**Para resetar o banco:** exclua o arquivo `estoque.db` e reinicie o servidor.

---

## Parar o servidor

No terminal onde o servidor está rodando, pressione:
```
Ctrl + C
```

---

## Problemas comuns

| Problema | Solução |
|---|---|
| `python` não reconhecido no Windows | Reinstale o Python marcando "Add to PATH" |
| Porta 5000 em uso | Mude para `app.run(port=5001)` no final do `app.py` |
| `ModuleNotFoundError: flask` | Rode `pip install flask` com o ambiente virtual ativo |
| No Mac, porta 5000 ocupada pelo AirPlay | Use `app.run(port=5001)` |

---

## Uso em rede local (outros computadores acessarem)

Para que outros computadores na mesma rede Wi-Fi acessem o sistema, altere a última linha do `app.py`:

```python
# Antes:
app.run(debug=True)

# Depois:
app.run(host='0.0.0.0', debug=True)
```

Então, nos outros computadores, acesse:
```
http://[IP_DO_SEU_COMPUTADOR]:5000
```

Para descobrir seu IP local:
- **Windows:** `ipconfig` no terminal → IPv4
- **Mac/Linux:** `ifconfig` ou `ip addr`

---

## Estrutura do banco de dados

```
categorias        produtos              movimentacoes
──────────        ────────────────      ─────────────────
id                id                    id
nome              nome                  produto_id → produtos.id
                  codigo (único)        tipo (entrada/saida/ajuste)
                  categoria_id          quantidade
                  quantidade            observacao
                  preco_custo           criado_em
                  preco_venda
                  estoque_min
                  criado_em
```

---

## Rodar como serviço do Windows (iniciar automático com o servidor)

Usando o **NSSM** (Non-Sucking Service Manager), o EstoqueApp vira um serviço do Windows — sobe sozinho quando o servidor liga e fica rodando em segundo plano, sem precisar abrir o cmd.

### 1. Baixar o NSSM

Acesse **https://nssm.cc/download** e baixe a versão mais recente.  
Extraia o zip. Dentro da pasta `win64` (ou `win32` se seu Windows for 32 bits), copie o arquivo `nssm.exe` para dentro da pasta do projeto:

```
C:\EstoqueApp\
├── nssm.exe       ← coloque aqui
├── app.py
├── requirements.txt
└── templates\
```

### 2. Descobrir o caminho completo do Python

Antes de configurar, você precisa saber onde o Python está instalado. Abra o cmd e rode:

```cmd
where python
```

Você verá algo como:
```
C:\Users\SeuNome\AppData\Local\Programs\Python\Python311\python.exe
```

Anote esse caminho — você vai precisar dele.

> **Se estiver usando ambiente virtual**, o caminho será diferente, por exemplo:  
> `C:\EstoqueApp\venv\Scripts\python.exe`  
> Use esse caminho no lugar.

### 3. Instalar o serviço

Abra o **cmd como Administrador** (clique com o botão direito no cmd → "Executar como administrador") e rode:

```cmd
cd C:\EstoqueApp
nssm install EstoqueApp
```

Uma janela de configuração vai abrir. Preencha assim:

| Campo | O que colocar |
|---|---|
| **Path** | Caminho do Python (ex: `C:\EstoqueApp\venv\Scripts\python.exe`) |
| **Startup directory** | Pasta do projeto (ex: `C:\EstoqueApp`) |
| **Arguments** | `app.py` |

Clique em **"Install service"**.

### 4. Iniciar o serviço

Ainda no cmd como Administrador:

```cmd
nssm start EstoqueApp
```

Pronto! O sistema já está rodando. Acesse `http://127.0.0.1:5000` no navegador para confirmar.

A partir de agora, toda vez que o servidor ligar, o EstoqueApp vai subir automaticamente.

### Comandos úteis do NSSM

```cmd
nssm stop EstoqueApp       # Para o serviço
nssm start EstoqueApp      # Inicia o serviço
nssm restart EstoqueApp    # Reinicia
nssm remove EstoqueApp     # Remove o serviço (desinstala)
nssm status EstoqueApp     # Verifica se está rodando
```

Você também pode gerenciar o serviço pelo **Gerenciador de Serviços do Windows**:  
`Win + R` → digite `services.msc` → procure "EstoqueApp".

### Verificar logs em caso de erro

Se o serviço não subir, o NSSM salva logs automaticamente. Para ver:

```cmd
nssm edit EstoqueApp
```

Vá na aba **"I/O"** e configure um arquivo de log para facilitar o diagnóstico.

---

*EstoqueApp — versão 1.0*
