# Brocade MEF3 Collector (SAN) — Ansible

Automação para **coletar utilizadores locais em switches SAN Brocade** via SSH e gerar ficheiros **MEF3** (1 ficheiro por switch), usando **Ansible** e um input simples (hostname + IP).

---

## Funcionalidades

- Coleta de utilizadores locais via `userconfig --show -a`
- Execução paralela via Ansible (SSH)
- Input simples: CSV / TXT com hostname e IP
- Geração de **1 MEF3 por switch**
- Naming padronizado:
  ```
  {CUSTOMER}-SAN_{HOSTNAME}_{YYYYMMDDHHMMSS}.mef3
  ```
- Normalização do campo **identity** via `gecos.txt` (formato canónico)
- Trailer técnico em **2 linhas** com `NOTaRealID-Ansible` + metadados `#kyndrylonly`

---

## Estrutura do Projeto

```
ansible/
├── gecos.txt
├── inventories/
│   └── san.yml
├── playbooks/
│   └── collect_san_brocade.yml
├── scripts/
│   ├── csv_to_san_inventory.py
│   └── generate_mef3_from_brocade_raw.py
├── outputs/
│   ├── raw/
│   └── mef3/
└── README.md
```

---

## Requisitos

- Python 3.8+
- Ansible 2.10+
- Acesso SSH aos switches Brocade
- Comando disponível no switch: `userconfig --show -a`

---

## Input (CSV / TXT)

Formato mínimo:

```
hostname,ip
INF_ALF_032_249824E_10133NP,192.168.251.64
```

Ou sem header (TAB ou espaços):

```
INF_ALF_032_249824E_10133NP    192.168.251.64
```

Separadores aceites:
- vírgula (,)
- ponto e vírgula (;)
- TAB
- múltiplos espaços

---

## Credenciais

As credenciais SSH **não são armazenadas**. Passe em runtime:

```
-e ansible_user=USERNAME -e ansible_password=PASSWORD
```

Pode ser adaptado para Ansible Vault.

---

## Normalização do identity (gecos.txt)

O ficheiro `gecos.txt` (na raiz do projeto) é a **fonte de verdade** para o formato canónico do campo `identity`.

Exemplos de formato:

- `PT/K/<id>/<org>/<Apelido, Nome>`
- `PT/F/<env>/<org>/<descrição>`

Regras (alto nível):
- Ao gerar o MEF3, o script tenta resolver `identity` usando `Account name` e/ou `Description`.
- Se encontrar correspondência no `gecos.txt`, usa a linha completa (canónica).
- Se não encontrar, aplica fallback (ex.: `Description` “limpo”) para não quebrar a geração.

> Mantém o `gecos.txt` atualizado conforme as contas esperadas no ambiente.

---

## Pipeline de Execução

### 1) CSV → Inventory Ansible

```
python3 scripts/csv_to_san_inventory.py hosts.csv inventories/san.yml --customer PTINF
```

Cria o grupo `san_brocade` com os hosts SAN.

---

### 2) Coleta via SSH (Brocade)

```
ansible-playbook -i inventories/san.yml playbooks/collect_san_brocade.yml   -e ansible_user=SEUUSER -e ansible_password=SUAPASS
```

Outputs brutos:

```
outputs/raw/<CUSTOMER>/<HOSTNAME>.<TIMESTAMP>.userconfig.txt
```

---

### 3) Geração do MEF3

```
python3 scripts/generate_mef3_from_brocade_raw.py outputs/raw outputs/mef3
```

Output final:

```
outputs/mef3/
└── PTINF-SAN_INF_ALF_032_249824E_10133NP_20260122143055.mef3
```

---

## Estrutura do MEF3

### Linhas de utilizador
- 1 linha por utilizador local
- 11 campos separados por `|`
- Campos principais: `customer`, `asset_class=S`, `asset_id`, `category=SAN`, `username`, `identity`, `status`, `role`

### Trailer técnico (2 linhas)

**Linha 1 (NOTaRealID-Ansible):**
```
PTINF|S|INF_ALF_100_8960F96_781016D|SAN|NOTaRealID-Ansible||00/V///2026-02-02-03.53.16:FN=iam_extract.ps1:VER=V2.0.74:CKSUM=3167295684|||#a:tricode#o:C:\ansible\GTS\uidext\tricode_devicename_date.mef3
```

**Linha 2 (metadados):**
```
#kyndrylonly #g:Ansible ### FINAL_TS=2026-02-02-03.54.34 PROCNUM=1:PROCSPEED=2295:MEM=17179332608:NETWORK=10000000000 10000000000 10000000000|0|
```

#### Formatos de timestamp
- Nome do ficheiro MEF3: `YYYYMMDDHHMMSS`
- Trailer (`00/V///...`) e `FINAL_TS`: `YYYY-MM-DD-HH.MM.SS`

> Nota (Windows path): se editares o script e usares um path como `C:\ansible\...`, em Python usa raw string (`r"C:\ansible\..."`) ou duplica as barras (`\\`) para evitar `unicodeescape`.

---

## Regras de Status

- `enable`: Enabled = Yes e Locked = No
- `disable`: qualquer outro caso

---

## Licença

Uso interno / compliance.
