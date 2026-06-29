# AUDIT TEMPLATE — Checklist de fin de chapitre

> À remplir AVANT de clore chaque session/chapitre.
> Si une case n'est pas cochée → on ne ferme PAS, on règle d'abord.
> Si plusieurs cases ne sont pas cochables → on reprend tout.

---

## Comment l'utiliser

1. Copie ce fichier sous le nom `AUDIT_SESSION_N.md` dans `docs/RECAPS/`
2. Remplis chaque section en répondant honnêtement
3. Si tu coches "❌ Non" sur une case critique → STOP, on règle d'abord
4. Une fois toutes les cases vertes → la session peut être fermée

---

# AUDIT — Session N (titre)

**Date** : YYYY-MM-DD
**Auditeur** : Claude + Badoun
**Durée de la session** : Xh

---

## 1. ALIGNEMENT AVEC LA SPEC (le plus critique)

Pour CHAQUE règle ICC implémentée pendant cette session, vérifier ligne par ligne :

- [ ] Toutes les règles touchées du `docs/ICC_SPEC.md` sont respectées dans le code
- [ ] Aucun paramètre arbitraire introduit sans justification documentée
- [ ] Aucun rafistolage (= patch rapide qui dévie de la spec)
- [ ] Body close only respecté partout (pas d'utilisation de high/low pour les cassures)
- [ ] Pas de lookahead (jamais de futur utilisé dans la détection)

**Si une case = ❌** : STOP. On reprend ce point. Pas de fermeture de session.

**Détails / écarts détectés** :
- ...

---

## 2. TESTS UNITAIRES

- [ ] Tous les fichiers de stratégie ajoutés ont leurs tests
- [ ] **100% des tests passent** (pas 99%, pas "presque tous")
- [ ] Tests couvrent les cas limites (bootstrap, edges, données plates)
- [ ] Tests couvrent les cas réels (random walks, sanity)
- [ ] Pas de test commenté/désactivé "à fixer plus tard"

**Résultat** : X/Y passent

**Si pas 100%** : STOP. Pas de fermeture tant que tout ne passe pas.

---

## 3. VALIDATION SUR DONNÉES RÉELLES

- [ ] Code testé sur ≥ 3 actifs différents (BTC, ETH, SOL minimum)
- [ ] Code testé sur ≥ 2 timeframes différents si applicable
- [ ] Tous les sanity checks passent (ordering, balance, lookahead, metadata)
- [ ] Comportement qualitatif cohérent avec le sens du marché

**Actifs validés** :
- ...

**Sanity checks** : X/Y verts

---

## 4. PERFORMANCE

- [ ] Temps d'exécution acceptable (<10s sur 5000 bars pour une stratégie complète)
- [ ] Pas de fuite mémoire évidente
- [ ] Pas de boucle qui scale en O(n²) sur les données

**Benchmark** :
- N bars : X secondes

---

## 5. CODE QUALITY

- [ ] Code lisible (noms explicites, commentaires sur la logique non-évidente)
- [ ] Fonctions courtes et focalisées (idéalement < 50 lignes)
- [ ] Pas de duplication évidente
- [ ] Types annotés (Python type hints) sur les fonctions principales
- [ ] Pas de `print()` de debug oubliés dans le code

---

## 6. DOCUMENTATION

- [ ] `JOURNAL.md` mis à jour avec entry de la session
- [ ] `RECAPS/SESSION_N_RECAP.md` créé et complet
- [ ] `ARCHITECTURE.md` mis à jour si nouveaux fichiers
- [ ] `ICC_SPEC.md` Statut d'implémentation mis à jour
- [ ] `README.md` toujours à jour si nécessaire

---

## 7. SAUVEGARDE

- [ ] Git commit fait avec message descriptif
- [ ] `scripts/backup.sh` lancé (ZIP daté créé)
- [ ] Backup sur disque externe planifié ou fait

---

## 8. PROCHAINES ÉTAPES

- [ ] Prochaine session définie clairement
- [ ] Estimation de durée
- [ ] Dépendances identifiées
- [ ] Risques identifiés

**Prochaine session** : Session N+1 — ...
**Estimation** : Xh
**Risques** : ...

---

## 9. BILAN HONNÊTE

### Ce qui a bien marché
- ...

### Ce qui aurait pu être mieux
- ...

### Niveau de confiance dans le travail
- [ ] Élevé (je dormirais sereinement avec ce code en production)
- [ ] Moyen (ça marche mais je veux re-tester demain)
- [ ] Bas (on devrait reprendre)

**Si bas** : ON REPREND. Pas de fermeture de session.

---

## 10. SIGNATURES

- Date de clôture : YYYY-MM-DD
- Tests : ✓ / ✗
- Validation réelle : ✓ / ✗
- Audit : ✓ / ✗
- Documentation : ✓ / ✗

**Verdict final** :
- [ ] ✅ SESSION FERMÉE (toutes cases vertes)
- [ ] ⚠ SESSION PARTIELLE (cases non-bloquantes vides, à compléter en début de session suivante)
- [ ] ❌ SESSION RÉOUVERTE (au moins une case critique non cochée)

---

*Template v1 — 10 Mai 2026*
