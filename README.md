# Kanban RASA

Tableau Kanban partagé (Arnaud / Charles / Commun) pour l'équipe RASA.

- 3 tableaux, 3 colonnes (À faire / En cours / Fait)
- Glisser-déposer des cartes dans un tableau **et entre les tableaux**
- Ajouter / éditer / supprimer des cartes
- Bouton **✨ IA** : propose des tâches (gemma4 via groslolo, repli Gemini)
- **Historique** de toutes les modifications
- État partagé côté serveur (JSON sur volume `/data`), rafraîchi toutes les 5 s

## Lancer en local
```
pip install -r requirements.txt
uvicorn app:app --port 8000
```

## Variables d'env
- `OLLAMA_HOST` (défaut groslolo `http://100.77.245.32:11434`)
- `OLLAMA_FALLBACK_HOST`, `OLLAMA_MODEL` (défaut `gemma4:latest`)
- `GEMINI_API_KEY` (dernier repli)
- `DATA_DIR` (défaut `/data` en conteneur)
