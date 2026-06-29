# Trading Bot v2 — ICC Implementation

> Bot de trading crypto basé sur la méthodologie **ICC** (Indication-Correction-Continuation)
> de TradesSAI. Implémentation rigoureuse, testée, validée sur 12 ans de données.

---

## 🎯 Pour reprendre rapidement (lis ça si tu es nouveau / si tu reviens)

### Si tu n'as jamais lu ce projet
1. **`docs/JOURNAL.md`** ← lis ça d'abord (chronologie complète)
2. **`docs/ARCHITECTURE.md`** ← carte du projet
3. **`docs/ICC_SPEC.md`** ← la spec de référence (toute déviation est interdite)

### Si tu reprends après plusieurs jours
1. Va dans **`docs/RECAPS/`** → lis le dernier `SESSION_N_RECAP.md`
2. Dans le terminal :
   ```bash
   cd ~/Desktop/trading-bot-v2
   source ../trading-bot/venv/bin/activate
   python tests/test_icc_structure.py  # doit afficher "22/22 passed"
   ```
3. Si tout marche, dis à Claude : *"Reprends Session N+1, voici le JOURNAL et le dernier RECAP"*

---

## 📊 Statut actuel

**Date** : 10 Mai 2026
**Session courante** : Session 2 ✅ Complète
**Prochaine session** : Session 3 (Order Blocks — TU#3)

### Ce qui marche
- ✅ Pipeline de données multi-TF (8 cryptos × Daily/H4/H1 sur jusqu'à 12 ans)
- ✅ Détection structure ICC fidèle aux TU#1 + TU#2 (22 tests passent)
- ✅ Validé sur BTC, ETH, SOL (daily) + BTC (H4)
- ✅ Système Git + sauvegarde automatique
- ✅ Documentation complète

### Ce qui ne marche pas encore
- 🔨 Order Blocks (TU#3) — Session 3 à venir
- 🔨 Cycle ICC complet (TU#4) — Session 4
- 🔨 Walk-forward final — Session 5

---

## 🏗️ Structure du projet

```
trading-bot-v2/
├── README.md              ← Ce fichier (point d'entrée)
├── docs/                  ← Documentation
│   ├── JOURNAL.md         ← Chronologie cumulative
│   ├── ARCHITECTURE.md    ← Carte du projet
│   ├── ICC_SPEC.md        ← Spec ICC complète
│   ├── AUDIT_TEMPLATE.md  ← Checklist fin de chapitre
│   └── RECAPS/            ← Recap par session
├── data/                  ← Pipeline de données
├── strategies/            ← Logique de trading (icc_structure.py ✅)
├── backtest/              ← Moteurs de backtest
├── tests/                 ← Tests unitaires
├── scripts/               ← Utilitaires (backup.sh, validate_icc_on_real_data.py)
├── cache/                 ← Données téléchargées (530+ MB, exclu de Git)
└── backups/               ← ZIP datés (exclu de Git)
```

---

## 🚀 Commandes utiles

### Tests
```bash
# Tous les tests structure ICC
python tests/test_icc_structure.py

# Tests legacy
python tests/test_engine.py
python tests/test_trend.py
```

### Validation visuelle ICC
```bash
python scripts/validate_icc_on_real_data.py BTC daily
python scripts/validate_icc_on_real_data.py ETH daily
python scripts/validate_icc_on_real_data.py BTC h4
python scripts/validate_icc_on_real_data.py SOL daily
```

### Sauvegarde
```bash
# Sauvegarde rapide (message auto-généré)
bash scripts/backup.sh

# Sauvegarde avec message custom
bash scripts/backup.sh "Session 3 complete - OB detection"
```

### Gestion des données
```bash
# État du cache
python data/validate_data.py

# Re-parser un ZIP Kraken (si on veut ajouter un actif)
python data/parse_kraken_zip.py ~/path/to/kraken_dump/ --extracted
```

---

## 📏 Règles d'or du projet (NON-NÉGOCIABLES)

1. **Pas de rafistolage** : si on dévie de la spec ICC, on s'arrête
2. **Audit avant chaque clôture** de chapitre (voir `docs/AUDIT_TEMPLATE.md`)
3. **Tests obligatoires** pour chaque fichier de stratégie
4. **Walk-forward systématique** pour valider toute stratégie
5. **Body close uniquement** pour les cassures (TU#1)
6. **No lookahead** : pas de futur dans la détection
7. **Sauvegarde** à chaque fin de session
8. **Récap quotidien** dans `docs/RECAPS/`

---

## 🔧 Configuration

### Dependencies (déjà installées dans venv)
```
ccxt 4.5.52
pandas
numpy
scipy
pyarrow
pyyaml
yfinance  (optionnel : pip install yfinance --break-system-packages)
```

### venv
```bash
source ~/Desktop/trading-bot/venv/bin/activate
```

---

## 🆘 Si quelque chose ne marche pas

### "Tests ne passent plus"
- Vérifier que `cache/` est intact
- Re-lancer `python data/validate_data.py`
- Vérifier la version de pandas

### "Git n'existe pas"
- `cd ~/Desktop/trading-bot-v2`
- `git init -q && git add . && git commit -m "Initial commit"`

### "Le script backup.sh fail"
- `chmod +x scripts/backup.sh`

### "Claude ne se souvient pas de la session précédente"
- C'est normal. Donne-lui le `JOURNAL.md` + dernier `RECAP`.
- Claude reprendra exactement où on s'était arrêté.

---

## 📞 Pour résumer si tu parles à Claude (nouvelle session)

> "Bonjour Claude, je reprends le projet trading-bot-v2 (ICC).
> Le code est dans ~/Desktop/trading-bot-v2/.
> Le JOURNAL est dans docs/JOURNAL.md.
> Le dernier recap est dans docs/RECAPS/SESSION_N_RECAP.md.
> On était à la Session N. Lis le tout puis on reprend."

Claude saura quoi faire.

---

*Projet construit avec rigueur et discipline. 10 Mai 2026.*
