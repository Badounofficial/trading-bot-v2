# 🛟 TRIP_PLAYBOOK — Trading Bot v2 Voyage

> **Document opérationnel** : que faire pendant le voyage de 10 jours.
> Lis cette page sur ton iPhone via Termius (`cat docs/TRIP_PLAYBOOK.md`)
> ou sur GitHub (web).

**Date départ** : ~21 mai 2026
**Durée** : 10 jours
**Mode** : Bot en autonomie, intervention via SSH iPhone si besoin

---

## 🆘 QUICK REFERENCE — Les 6 commandes essentielles

```bash
# 0. Toujours commencer par : se connecter au bon dossier + venv
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
source venv/bin/activate

# 1. CHECK SANTÉ — la commande à lancer le matin
python -m scripts.check_bot_health

# 2. VOIR LES 100 DERNIÈRES LIGNES DE LOG (today)
tail -100 paper_trading/logs/$(date -u +%Y-%m-%d).jsonl

# 3. SAVOIR SI LE BOT TOURNE (process Python)
ps aux | grep -i run_production | grep -v grep

# 4. TUER LE BOT (pour le relancer ensuite, kill propre)
# Si tu es sur le terminal qui le fait tourner : Ctrl+C
# Sinon, depuis n'importe quel SSH :
pkill -SIGINT -f run_production

# 5. RELANCER LE BOT (toujours après un kill propre)
nohup python -m scripts.run_production > /tmp/bot_output.log 2>&1 &
disown
# (Voir section "Relancer en mode détaché" plus bas pour explications)

# 6. SUIVRE LE BOT EN DIRECT (équivalent du terminal Mac)
tail -f /tmp/bot_output.log
# Ctrl+C pour sortir (ne tue PAS le bot, juste le tail)
```

---

## 📋 Table des matières

1. [Routine quotidienne — check matin](#routine)
2. [Lecture des notifs Telegram](#telegram)
3. [Scénario : Tu reçois une alerte HALT](#halt)
4. [Scénario : Bot crash / process disparu](#crash)
5. [Scénario : Mac s'est endormi](#sleep)
6. [Scénario : Pas de notif Telegram depuis 8h+](#silence)
7. [Scénario : check_bot_health affiche WARNING ou CRITICAL](#warning)
8. [Relancer en mode détaché (nohup)](#nohup)
9. [Numéros & ressources d'urgence](#urgence)

---

## <a name="routine"></a>1. Routine quotidienne — check matin

**Une fois par jour minimum**, idéalement le matin NY après ton réveil :

### Étape 1 — Vérifier Telegram en premier
Sur ton iPhone, ouvre Telegram et regarde tes notifs :
- ❤️ Heartbeat reçu à 12:00 UTC (= 08:00 NY été EDT) ? → ✅
- 📦 Backups reçus à 00:00 / 06:00 / 12:00 / 18:00 UTC ? → ✅
- 🚨 Aucun HALT ? → ✅

Si tout est ✅, **tu peux ne pas SSH** ce jour-là. Le bot va bien.

### Étape 2 — SSH si tu veux confirmer
Ouvre Termius → tap "Mac trading bot" → entre ton mot de passe Mac.

Puis :
```bash
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
source venv/bin/activate
python -m scripts.check_bot_health
```

**Verdict attendu** : `✅ HEALTHY — all checks pass`

Si oui, déconnecte (`exit` ou ferme Termius) et profite de ta journée NY. 🛟

---

## <a name="telegram"></a>2. Lecture des notifs Telegram

### ❤️ Heartbeat (1x/jour, 12:00 UTC = 08:00 NY)

```
❤️ Daily heartbeat
   Equity : $1,XXX.XX
   Open positions : N
   PnL today : 📈 +$XX.XX (or 📉 -$XX.XX)
   Trades today : M
   Bot status: RUNNING ✓
```

**Ce que ça veut dire** : bot vivant, voici le résumé du jour.

**Signaux à surveiller** :
- `Bot status: RUNNING ✓` → ✅
- `Bot status: HALTED` → 🚨 [Aller à section HALT](#halt)
- Drawdown ou PnL très négatif (>-10%) → vigilance, voir section HALT

### 📦 Backup .db.gz (4x/jour, à 00h, 06h, 12h, 18h UTC)

```
📦 Trading bot DB backup
   Snapshot: state_2026-05-XXTHHmm-mmS.db.gz
   Size: 0.X KB
   Time: 2026-05-XXTHH:MM:SS.XXXXXXXZ
```

**Ce que ça veut dire** : la DB du bot a été sauvegardée sur Telegram. Si jamais tout crashe, tu peux **télécharger ce fichier depuis Telegram** et restaurer.

**Pas d'action requise**. C'est juste la preuve que ça marche.

### 🚨 HALT (jamais, idéalement)

```
🚨 BOT HALTED
   Reason : XXX (Drawdown -X% OR Daily loss -Y%)
   Current equity : $XXX.XX
   Peak equity : $1,000.00
   All open positions have been closed.
   Bot will NOT open new trades until manual resume.
```

**Ce que ça veut dire** : le bot a atteint sa limite de risque, a fermé toutes positions, et **ne tradera plus** jusqu'à ce que tu le relances.

→ [Aller à la section HALT](#halt)

---

## <a name="halt"></a>3. Scénario : Tu reçois une alerte HALT

### Calme — c'est par design

Le bot HALT **fait ce qu'on a programmé** : limiter la perte. La situation est sous contrôle. **Pas d'urgence absolue**.

Tu as 2 options :

**Option A — Relancer maintenant** (si tu juges que c'est ok)
**Option B — Laisser HALTED jusqu'au retour** (si tu préfères jouer safe)

Le Playbook te guide pour décider.

---

### Étape 1 — Évaluer l'ampleur

```bash
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
source venv/bin/activate
python -m scripts.check_bot_health
```

Regarde :
- **Drawdown** : combien de % perdu ?
- **Equity actuel** vs **Peak equity** : la différence

### Étape 2 — Évaluer le contexte

```bash
# Voir les 100 dernières lignes du log d'aujourd'hui
tail -100 paper_trading/logs/$(date -u +%Y-%m-%d).jsonl
```

Cherche les événements proches du HALT :
- Y a-t-il eu **plusieurs trades qui ont perdu** ? → normal, drawdown s'est creusé
- Y a-t-il eu **1 seul trade catastrophique** ? → vérifie le slippage
- Y a-t-il eu des **erreurs Kraken** (timeout, etc.) ? → bug technique, pas marché

### Étape 3 — Grille de décision

| Situation | Action recommandée |
|---|---|
| Drawdown = -15% pile, plusieurs trades, marché volatile | **Relancer** : le système a bien fonctionné, on continue |
| Drawdown = -16% avec 1 seul trade énorme | **Investiguer** : slippage ? bug ? puis décider |
| Drawdown = -15% mais Kraken timeouts dans logs | **Laisser HALTED** : bug technique, ne pas relancer aveuglément |
| Tu es fatigué / nuit / pas envie | **Laisser HALTED** : ça peut attendre demain |

### Étape 4 — Si tu décides de relancer

**Modifier l'état du bot dans la DB** : on doit passer status de HALTED → RUNNING.

```bash
sqlite3 paper_trading/state.db "UPDATE bot_state SET status='RUNNING', halt_reason=NULL, halt_timestamp=NULL WHERE id=1"
```

**Vérifier que c'est bien fait** :
```bash
python -m scripts.check_bot_health
```

Doit afficher `Status : RUNNING` (et plus de halt_reason).

**Important** : si le bot est encore en train de tourner (process actif), le restart automatique aura lieu au prochain cycle. Si le bot a aussi été tué (process disparu), [aller à la section Crash](#crash).

---

## <a name="crash"></a>4. Scénario : Bot crash / process disparu

### Symptôme
- `check_bot_health` affiche que la DB n'a pas été mise à jour depuis > 75 min
- → CRITICAL: "Last cycle is X min old (expected < 75)"

### Diagnostic

```bash
# Est-ce que le process Python tourne encore ?
ps aux | grep -i run_production | grep -v grep
```

- **Si tu vois une ligne avec `python -m scripts.run_production`** → le bot tourne, c'est peut-être juste la DB qui n'a pas été mise à jour. Vérifie `tail -f /tmp/bot_output.log` pour voir ce qu'il fait.
- **Si rien n'apparaît** → le bot est mort. Tu dois le relancer.

### Relance après crash

```bash
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
source venv/bin/activate
nohup python -m scripts.run_production > /tmp/bot_output.log 2>&1 &
disown
```

(Voir [Relancer en mode détaché](#nohup) pour les détails)

### Vérifier que ça tourne

```bash
ps aux | grep -i run_production | grep -v grep
```

Doit afficher 1 ligne avec ton processus.

```bash
tail -20 /tmp/bot_output.log
```

Doit afficher le dump initial + `Sleeping XXX.Xs until next cycle...`

---

## <a name="sleep"></a>5. Scénario : Mac s'est endormi

### Symptôme
- Plus aucune notif Telegram depuis plusieurs heures
- Tu essaies SSH → "Connection timeout" ou "Host unreachable"

### Diagnostic

Sur l'iPhone, ouvre **l'app Tailscale** :
- Si ton Mac n'apparaît plus dans la liste → Mac dort ou Wi-Fi déconnecté
- Si Mac apparaît mais "offline" / grisé → Mac dort

### Ce que tu peux faire à distance

**Honnêtement : pas grand-chose.**

Options :
1. **Wake-on-LAN** : envoyer un signal au routeur pour réveiller le Mac. Pas configuré pour ce projet (complexe).
2. **Demander à quelqu'un sur place** : la personne ouvre le capot ou bouge la souris.
3. **Attendre ton retour** : la DB est intacte, le bot reprendra quand le Mac revient.

### Prévention (à faire AVANT le voyage)

Voir section [Configuration "Mac ne dort jamais"](#mac-config) — à faire la veille du départ.

---

## <a name="silence"></a>6. Scénario : Pas de notif Telegram depuis 8h+

### Causes possibles
1. **Telegram client toi-même** est en panne → vérifie autres conversations
2. **Bot Telegram token expiré** → mais ce serait étonnant
3. **Mac dort ou crash** → voir sections [Crash](#crash) ou [Sleep](#sleep)
4. **Pas de cycle de backup atteint** → si tu n'as raté que 1 fenêtre (6h), c'est presque normal

### Vérification

SSH depuis iPhone et lance :
```bash
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
source venv/bin/activate
python -m scripts.check_bot_health
```

Le rapport te dira immédiatement si le bot tourne ou pas.

---

## <a name="warning"></a>7. Scénario : check_bot_health affiche WARNING ou CRITICAL

### WARNINGS communs

**"Last Telegram backup was Xh ago (expected every 6h)"**
- Si X est entre 6 et 8h : pas grave, attendre la prochaine fenêtre
- Si X > 12h : possible problème Telegram. Vérifier `tail logs` pour erreurs.

**"No Telegram backup ever sent"**
- Possible si la DB a été reset
- Sans gravité, prochain envoi à la prochaine fenêtre programmée

### CRITICAL communs

**"Last cycle is XX min old (expected < 75)"**
- → [Section Crash](#crash)

**"Invariant violation: equity - (cash + open_value) = $X.YY"**
- 🚨 Bug comptable dans le bot
- Action : envoyer screenshot du health check + 100 lignes de log à Claude pour analyse
- En attendant : laisse HALTED (`sqlite3 ... UPDATE bot_state SET status='HALTED'`)

---

## <a name="nohup"></a>8. Relancer en mode détaché (nohup)

### Pourquoi ?

Si tu relances le bot dans une session SSH simple (`python -m scripts.run_production`), **le bot s'arrête** quand tu fermes SSH. C'est pas ce qu'on veut.

`nohup` + `&` + `disown` permettent de :
1. Lancer le bot
2. Le détacher de la session SSH
3. Garder le bot en vie même après déconnexion

### La commande complète

```bash
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
source venv/bin/activate
nohup python -m scripts.run_production > /tmp/bot_output.log 2>&1 &
disown
```

### Décomposition

- `nohup` : "no hangup" — ignore le signal de fermeture SSH
- `python -m scripts.run_production` : lance le bot
- `> /tmp/bot_output.log` : redirige stdout vers un fichier
- `2>&1` : redirige stderr vers stdout (donc tout va dans le log)
- `&` : lance en arrière-plan
- `disown` : détache complètement le process de la session shell

### Vérifier ensuite

```bash
ps aux | grep -i run_production | grep -v grep
```

Tu devrais voir 1 ligne. **Note le PID** (2e colonne).

```bash
tail -f /tmp/bot_output.log
```

Tu vois les logs du bot en temps réel. Ctrl+C pour sortir du tail (sans tuer le bot).

### Pour tuer le bot plus tard

```bash
pkill -SIGINT -f run_production
```

Le bot reçoit Ctrl+C (signal SIGINT), affiche le message "State preserved", et termine proprement.

---

## <a name="urgence"></a>9. Numéros & ressources d'urgence

### Documentation Claude / projet
- `docs/JOURNAL.md` — historique du projet
- `docs/RECAPS/BUGS_FOUND.md` — détail des 8 bugs résolus
- `docs/ARCHITECTURE.md` — vue d'ensemble fichiers/modules

### Logs et données
- `paper_trading/state.db` — DB principale
- `paper_trading/backups/` — snapshots locaux
- `paper_trading/logs/YYYY-MM-DD.jsonl` — événements bot
- `paper_trading/.last_telegram_backup` — tracker Telegram

### En cas de bug que tu ne comprends pas

1. Ouvre **Claude.ai** sur l'iPhone
2. Démarre une nouvelle conversation OU revient sur la dernière conversation où on a bossé sur le bot
3. Copie-colle :
   - Sortie de `check_bot_health`
   - Sortie de `tail -100 ...jsonl`
   - Description du problème
4. Je t'aide à analyser

### Ressources Tailscale (si SSH ne marche plus)

- App Tailscale iPhone : doit montrer Mac en "Online"
- Si Mac "Offline" dans Tailscale → Mac dort ou Wi-Fi déco
- Tailscale admin : https://login.tailscale.com/admin/machines (depuis Safari)

---

## <a name="mac-config"></a>📌 Annexe — Configuration "Mac ne dort jamais"

### ✅ AVANT le voyage — empêcher Mac de dormir

**Cette config a été appliquée le 16 mai 2026** (et reste active jusqu'à ce que tu la changes au retour).

Réglages actifs en permanence pour 12 jours (10 j voyage + 2 j marge) :

```bash
sudo pmset -a sleep 0          # système ne dort jamais
sudo pmset -a displaysleep 0   # écran ne dort jamais
sudo pmset -a disksleep 0      # disque ne dort jamais
sudo pmset -c disablesleep 1   # capot fermé OK (sur secteur)
```

**Vérification** :
```bash
pmset -g
```

Tu dois voir :
```
SleepDisabled   1
sleep           0
displaysleep    0
disksleep       0
```

### 🔋 Pendant le voyage — règles strictes

- ✅ Mac branché secteur 24/7
- ✅ Capot peut être ouvert OU fermé (avec `SleepDisabled=1` ça marche dans les 2 cas)
- ✅ Wi-Fi connecté (Tailscale a besoin d'internet)
- ❌ Ne PAS débrancher le Mac du secteur
- ❌ Ne PAS lancer une mise à jour macOS (peut redémarrer)
- ❌ Ne PAS éteindre le Mac

### 🏠 AU RETOUR — restaurer la veille normale

**Une fois rentré du voyage**, lance ces 4 commandes pour réactiver la veille normale :

```bash
# Restaurer comportement par défaut (économie d'énergie)
sudo pmset -a sleep 10          # dort après 10 min inactif
sudo pmset -a displaysleep 10   # écran dort après 10 min
sudo pmset -a disksleep 10      # disque dort après 10 min
sudo pmset -c disablesleep 0    # capot fermé = veille (normal)
```

**Vérification** :
```bash
pmset -g
```

Doit afficher :
```
SleepDisabled   0
sleep           10
displaysleep    10
disksleep       10
```

### 💡 Pourquoi c'est important de restaurer

- **Énergie** : Mac qui ne dort jamais consomme 5-10× plus
- **Usure** : SSD et batterie souffrent d'un usage 24/7
- **Sécurité** : Mac toujours actif = plus vulnérable
- **Économie d'écran** : OLED/écran qui ne dort jamais peut développer un burn-in

→ La config "voyage" est **explicitement temporaire**.

### ⚙️ Lance caffeinate au démarrage du bot (optionnel)

Si tu veux double-sécurité en parallèle de pmset :

```bash
caffeinate -i -t 1036800 &  # 12 jours en secondes
```

**Note** : `pmset` (config système) est plus robuste que `caffeinate` (process utilisateur). Si `pmset` est bien configuré, `caffeinate` est superflu. Mais ça ne coûte rien de doubler.

---

## 🎯 État avant le voyage — checklist

À vérifier la veille du départ :

- [ ] Bot tourne sans erreur depuis 5+ jours (burn-in)
- [ ] check_bot_health affiche HEALTHY
- [ ] Telegram heartbeat reçu hier à 12h UTC
- [ ] Telegram backup reçu hier à 18h UTC
- [ ] SSH iPhone fonctionne (test à la maison)
- [ ] Mac branché secteur
- [ ] caffeinate actif (vérifier `ps aux | grep caffeinate`)
- [ ] Routeur Wi-Fi qui ne s'éteint pas la nuit
- [ ] App Tailscale iPhone qui montre Mac "Online"
- [ ] App Termius iPhone qui se connecte au Mac

---

## 💌 Mot final pour ton voyage

Le bot a été conçu pour fonctionner **sans toi**. Tu as :
- 3 niveaux de backup (DB + locaux + Telegram cloud)
- Système de monitoring (heartbeat + alertes)
- Outil de health check
- Accès distant SSH sécurisé

**Tu peux profiter de NY.** Reviens vers le bot **seulement** :
- Le matin pour vérifier les notifs Telegram (2 min)
- Si tu reçois une alerte HALT (procédure ci-dessus)
- Une fois en milieu de voyage par sécurité (J+5)

Bonne route, Badoun. Le bot t'attend au retour. 🛟✨

---

*Document créé le 16 mai 2026 — Version 1.1*
*v1.1 : ajout de la section "AU RETOUR — restaurer la veille normale" + détails de la config "no sleep" déjà appliquée le 16 mai*
*Mis à jour : voir git log de docs/TRIP_PLAYBOOK.md*
