# Brocade MEF3 Collector (MEF)

Automação para **coleta de utilizadores locais em switches SAN Brocade** via SSH, com geração de ficheiros **MEF3** (1 ficheiro por switch), usando **Ansible** e um **CSV simples (hostname + IP)** como entrada.

O objetivo é suportar processos de **compliance e auditoria**, garantindo execução paralela, rastreabilidade e naming padronizado.

---

## Funcionalidades

- Coleta de utilizadores locais via `userconfig --show -a`
- Execução paralela via Ansible (SSH)
- Entrada simples: CSV / TXT com hostname e IP
- Geração de **1 MEF3 por switch**
- Naming padronizado:
  ```
  {CUSTOMER}-SAN_{HOSTNAME}_{YYYYMMDDHHMMSS}.mef3
  ```
- Separação lógica SAN (preparado para Storage no futuro)
- Parser robusto (CSV, TSV, espaços)
- Sem dependência de inventário Excel

---

## Estrutura do Projeto

```
ansible/
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

As credenciais SSH **não são armazenadas**.

São passadas em runtime:

```
-e ansible_user=USERNAME -e ansible_password=PASSWORD
```

Pode ser facilmente adaptado para **Ansible Vault**.

---

## Pipeline de Execução

### 1. CSV → Inventory Ansible

```
python3 scripts/csv_to_san_inventory.py hosts.csv inventories/san.yml --customer PTINF
```

Cria o grupo `san_brocade` com os hosts SAN.

---

### 2. Coleta via SSH (Brocade)

```
ansible-playbook -i inventories/san.yml playbooks/collect_san_brocade.yml \
  -e ansible_user=SEUUSER -e ansible_password=SUAPASS
```

Outputs brutos:
```
outputs/raw/<CUSTOMER>/<HOSTNAME>.<TIMESTAMP>.userconfig.txt
```

---

### 3. Geração do MEF3

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

- 1 linha por utilizador local
- 11 campos separados por `|`
- Linha final com `NOTaRealID` (trailer técnico)

Campos principais:
- customer
- asset_class = S
- asset_id = hostname
- category = SAN
- username
- identity (Description)
- status (enable / disable)
- role

---

## Regras de Status

- `enable`: Enabled = Yes e Locked = No
- `disable`: qualquer outro caso

---

## Requisitos

- Python 3.8+
- Ansible 2.10+
- Acesso SSH aos switches Brocade
- Comando disponível: `userconfig --show -a`

---

## Roadmap

- Agendamento (cron)
- Interface Web

---

## Licença

Uso interno / compliance.
