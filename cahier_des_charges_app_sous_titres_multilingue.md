# Cahier des charges technique — Application de génération de sous-titres multilingues à partir de vidéos

## 1. Résumé du projet

Créer une application desktop permettant à un utilisateur de :

- importer une vidéo locale depuis son ordinateur ou un disque dur externe ;
- extraire l'audio de cette vidéo ;
- générer automatiquement des sous-titres synchronisés dans la langue source ;
- télécharger ces sous-titres au format standard (`.srt` et `.vtt`) ;
- traduire ces sous-titres vers plusieurs langues cibles ;
- télécharger chaque version traduite sous forme de fichiers de sous-titres habituels.

L'application doit être pensée pour une **V1 solide, simple et maintenable**, avec une architecture suffisamment propre pour permettre une V2 plus avancée ensuite.

---

## 2. Objectif produit

### Objectif principal
Permettre à un utilisateur non technique de produire rapidement des sous-titres exploitables pour une vidéo locale, sans devoir manipuler des scripts, ffmpeg ou des API manuellement.

### Proposition de valeur
- workflow simple ;
- génération rapide ;
- export standard compatible avec les lecteurs vidéo ;
- traduction multi-langue ;
- respect maximal de la structure temporelle des sous-titres.

---

## 3. Périmètre

## 3.1 Périmètre V1

La V1 doit permettre :

1. import d'une vidéo locale ;
2. détection des métadonnées vidéo de base ;
3. extraction audio ;
4. choix éventuel de la piste audio si plusieurs pistes existent ;
5. transcription de l'audio avec timestamps de segments ;
6. génération d'un fichier de sous-titres source (`.srt`, `.vtt`) ;
7. prévisualisation textuelle simple des segments ;
8. traduction vers une ou plusieurs langues cibles ;
9. génération et téléchargement des sous-titres traduits ;
10. suivi d'état du traitement ;
11. gestion des erreurs principales ;
12. suppression automatique des fichiers temporaires.

## 3.2 Hors périmètre V1

Ne pas implémenter en V1 :

- édition manuelle avancée type éditeur professionnel de sous-titres ;
- waveform audio visuelle ;
- incrustation directe des sous-titres dans la vidéo ;
- OCR de sous-titres déjà présents à l'image ;
- reconnaissance de locuteurs ;
- diarisation ;
- alignement mot à mot visible dans l'interface ;
- synchronisation collaborative ;
- compte utilisateur cloud ;
- stockage distant permanent.

## 3.3 Périmètre V2 possible

- éditeur visuel de sous-titres ;
- fusion / split manuel de segments ;
- export `.ass` ;
- choix du style de sous-titrage ;
- burn-in des sous-titres dans la vidéo ;
- traduction avec glossaire ;
- historique local des projets ;
- file d'attente multi-traitements ;
- mode 100 % local offline via moteur STT local.

---

## 4. Utilisateurs cibles

- créateurs de contenu ;
- utilisateurs souhaitant sous-titrer des vidéos personnelles ou des mini-films ;
- monteurs débutants ;
- utilisateurs non techniques ayant des vidéos stockées localement.

---

## 5. User stories

### User stories principales

- En tant qu'utilisateur, je veux sélectionner une vidéo locale afin de lancer une génération de sous-titres.
- En tant qu'utilisateur, je veux choisir la langue source en automatique ou manuellement.
- En tant qu'utilisateur, je veux récupérer un fichier `.srt` ou `.vtt` téléchargeable.
- En tant qu'utilisateur, je veux traduire les sous-titres dans plusieurs langues.
- En tant qu'utilisateur, je veux voir l'avancement du traitement.
- En tant qu'utilisateur, je veux être averti si la vidéo est trop lourde ou si le traitement échoue.
- En tant qu'utilisateur, je veux conserver les timecodes d'origine lors de la traduction.
- En tant qu'utilisateur, je veux choisir un mode rapide ou un mode qualité.

### User stories secondaires

- En tant qu'utilisateur, je veux choisir la piste audio si la vidéo en possède plusieurs.
- En tant qu'utilisateur, je veux obtenir des noms de fichiers de sortie cohérents.
- En tant qu'utilisateur, je veux supprimer les fichiers temporaires après export.

---

## 6. Exigences fonctionnelles détaillées

## 6.1 Import vidéo

L'application doit :

- accepter le glisser-déposer et la sélection via explorateur de fichiers ;
- accepter au minimum les formats : `mp4`, `mov`, `mkv`, `avi`, `webm` ;
- vérifier que le fichier est lisible ;
- afficher les informations de base : nom, taille, durée, format, nombre de pistes audio ;
- refuser proprement les formats non supportés.

## 6.2 Analyse média

L'application doit utiliser `ffprobe` pour :

- lire la durée ;
- détecter les flux audio ;
- identifier les indexes de pistes audio ;
- remonter les métadonnées utiles si disponibles : langue audio, codec, nombre de canaux.

## 6.3 Choix de la piste audio

- Si une seule piste audio existe : sélection automatique.
- Si plusieurs pistes audio existent : l'interface doit proposer la liste des pistes.
- Une piste doit être marquée par défaut, mais l'utilisateur doit pouvoir en choisir une autre.

## 6.4 Extraction audio

L'application doit :

- extraire la piste audio sélectionnée via `ffmpeg` ;
- normaliser si besoin en mono / 16 kHz ou un format compatible avec le moteur STT choisi ;
- permettre un mode de compression si nécessaire pour respecter les limites de taille ;
- découper l'audio en chunks si sa taille dépasse le seuil accepté par l'API.

## 6.5 Transcription

L'application doit :

- envoyer l'audio au moteur de transcription ;
- récupérer une transcription structurée avec timestamps de segments ;
- associer chaque segment à : `start`, `end`, `text` ;
- proposer deux profils :
  - **Rapide** ;
  - **Qualité**.

### Contraintes transcription

- La langue source peut être :
  - auto-détectée ;
  - forcée par l'utilisateur.
- La transcription doit être exploitée même si elle est partielle.
- Les segments doivent pouvoir être fusionnés / nettoyés avant export.

## 6.6 Génération de sous-titres source

L'application doit générer :

- un fichier `.srt` ;
- un fichier `.vtt`.

### Règles minimales de formatage

- timecodes valides ;
- suppression des segments vides ;
- trim des espaces superflus ;
- remplacement des sauts de ligne aberrants ;
- limitation optionnelle de longueur par ligne ;
- maintien d'un ordre chronologique strict ;
- correction des overlaps évidents si possible.

## 6.7 Prévisualisation

La V1 doit proposer une preview simple :

- liste des segments ;
- numéro du segment ;
- timecode début / fin ;
- texte ;
- version source et version traduite si disponible.

Pas d'édition complexe en V1, mais une lecture simple est nécessaire pour contrôle visuel.

## 6.8 Traduction

L'application doit permettre :

- la sélection d'une ou plusieurs langues cibles ;
- la traduction **segment par segment** à partir des sous-titres source ;
- la conservation des mêmes timecodes que la version source ;
- la génération d'un fichier de sortie par langue.

### Langues cibles recommandées en V1

- français ;
- anglais ;
- espagnol ;
- allemand.

Optionnel si simple à ajouter proprement :

- arabe ;
- portugais.

### Règles de traduction

- ne jamais modifier les timecodes ;
- préserver l'ordre des segments ;
- éviter les traductions trop longues ;
- permettre une stratégie de raccourcissement si le texte dépasse un seuil ;
- préserver les noms propres autant que possible.

## 6.9 Export

L'application doit permettre de télécharger :

- le sous-titre source en `.srt` ;
- le sous-titre source en `.vtt` ;
- chaque version traduite en `.srt` ;
- chaque version traduite en `.vtt`.

### Convention de nommage proposée

- `nomvideo.original.srt`
- `nomvideo.original.vtt`
- `nomvideo.fr.srt`
- `nomvideo.en.srt`
- `nomvideo.es.srt`
- `nomvideo.de.srt`

## 6.10 Gestion d'état

Le frontend doit afficher des états explicites :

- prêt ;
- analyse vidéo ;
- extraction audio ;
- découpage audio ;
- transcription ;
- post-traitement ;
- traduction ;
- export prêt ;
- erreur.

## 6.11 Nettoyage

Le système doit supprimer les fichiers temporaires après :

- export terminé ;
- annulation ;
- échec terminal.

Un mode debug pourra conserver les artefacts localement pour diagnostic.

---

## 7. Exigences non fonctionnelles

## 7.1 Performance

- l'interface doit rester réactive pendant les traitements ;
- les traitements longs doivent être gérés en tâche asynchrone locale ;
- le backend ne doit pas bloquer le thread UI ;
- les gros fichiers doivent être chunkés proprement.

## 7.2 Maintenabilité

- code modulaire ;
- séparation claire UI / logique métier / intégrations externes ;
- services découplés ;
- configuration par variables d'environnement ;
- logs structurés.

## 7.3 Sécurité

- clé API jamais exposée côté frontend ;
- tous les appels API externes passent par le backend local ;
- validation stricte des chemins fichiers ;
- aucun accès arbitraire au système de fichiers hors répertoires autorisés ;
- nettoyage des temporaires ;
- limitation des tailles de fichiers.

## 7.4 Confidentialité

- préciser à l'utilisateur que l'audio est envoyé à un service distant si mode cloud ;
- ne pas stocker durablement les vidéos par défaut ;
- possibilité future d'un mode local offline.

## 7.5 Résilience

- gestion des timeouts API ;
- retries limités sur erreurs temporaires ;
- messages d'erreur compréhensibles ;
- fallback partiel si une traduction échoue mais la transcription source réussit.

---

## 8. Choix d'architecture recommandés

## 8.1 Architecture globale

### Recommandation V1

- **Application desktop** via **Tauri**
- **Frontend** : React + TypeScript
- **Backend local** : Python + FastAPI
- **Traitement média** : ffmpeg / ffprobe
- **Transcription / traduction cloud** : API Groq
- **Persistance locale** : minimale, orientée fichiers temporaires

### Pourquoi ce choix

- Tauri est plus léger qu'Electron pour une V1 desktop ;
- React + TypeScript facilitent une UI moderne ;
- Python est excellent pour ffmpeg, fichiers, audio, STT, conversion SRT/VTT ;
- FastAPI permet une API locale simple et claire ;
- Groq permet d'éviter une implémentation STT locale complexe en V1.

## 8.2 Alternative acceptable

Si Claude Code préfère une seule stack JS/TS :

- Tauri + React + TypeScript ;
- backend Rust minimal ou backend Node.js ;
- ffmpeg via process system ;
- API Groq via serveur local Node.

Mais la recommandation prioritaire reste **Python backend** pour la robustesse du pipeline média.

---

## 9. Architecture logique

## 9.1 Modules frontend

- `app-shell`
- `video-import`
- `job-config-panel`
- `audio-track-selector`
- `processing-status`
- `subtitle-preview`
- `downloads-panel`
- `settings-panel`
- `error-boundary`

## 9.2 Modules backend

- `api`
- `media_probe_service`
- `audio_extraction_service`
- `audio_chunking_service`
- `transcription_service`
- `subtitle_postprocess_service`
- `translation_service`
- `subtitle_export_service`
- `temp_file_manager`
- `job_manager`
- `config_service`
- `logging_service`

## 9.3 Flux de traitement

1. import vidéo ;
2. probe média ;
3. choix de piste ;
4. extraction audio ;
5. éventuelle conversion / compression ;
6. éventuel chunking ;
7. transcription ;
8. fusion et nettoyage des segments ;
9. génération du sous-titre source ;
10. traduction segmentée ;
11. génération des fichiers par langue ;
12. téléchargement / sauvegarde ;
13. nettoyage.

---

## 10. Pipeline détaillé

## 10.1 Étape 1 — Import
Entrée : chemin local vers vidéo.

Sortie : métadonnées minimales du fichier.

## 10.2 Étape 2 — Probe
Entrée : chemin vidéo.

Sortie :

```json
{
  "duration_seconds": 534.2,
  "video_format": "mp4",
  "audio_tracks": [
    {
      "index": 0,
      "codec": "aac",
      "channels": 2,
      "language": "en"
    }
  ]
}
```

## 10.3 Étape 3 — Extraction audio
Entrée : vidéo + index piste audio.

Sortie : fichier audio temporaire.

Exemple cible : WAV mono 16 kHz ou autre format optimisé selon la limite API.

## 10.4 Étape 4 — Chunking
Condition : si taille trop importante.

Sortie : liste ordonnée de chunks avec offsets temporels.

```json
[
  {"path": "chunk_001.wav", "offset_seconds": 0},
  {"path": "chunk_002.wav", "offset_seconds": 300}
]
```

## 10.5 Étape 5 — Transcription
Pour chaque chunk :

- appel API transcription ;
- récupération des segments ;
- réapplication de l'offset temporel.

Sortie consolidée :

```json
[
  {"start": 0.0, "end": 2.5, "text": "Hello and welcome."},
  {"start": 2.6, "end": 5.1, "text": "Today we will..."}
]
```

## 10.6 Étape 6 — Post-traitement segments
Règles :

- concaténer les segments trop courts si pertinent ;
- éviter les doublons ;
- corriger les légers overlaps ;
- supprimer les segments vides ;
- nettoyer ponctuation et espaces.

## 10.7 Étape 7 — Export source
Convertir les segments nettoyés vers :

- `.srt`
- `.vtt`

## 10.8 Étape 8 — Traduction
Entrée : segments source.

Sortie : segments traduits avec **mêmes timestamps**.

Ne pas traduire l'ensemble brut sans structure. Traduire segment par segment ou par petits lots structurés.

## 10.9 Étape 9 — Export multilingue
Générer un fichier par langue cible et par format.

---

## 11. Contrats de données

## 11.1 Objet SubtitleSegment

```ts
interface SubtitleSegment {
  id: string;
  start: number;
  end: number;
  text: string;
}
```

## 11.2 Objet TranslatedSubtitleSegment

```ts
interface TranslatedSubtitleSegment {
  id: string;
  start: number;
  end: number;
  sourceText: string;
  translatedText: string;
  targetLanguage: string;
}
```

## 11.3 Objet JobConfig

```ts
interface JobConfig {
  inputVideoPath: string;
  audioTrackIndex: number;
  sourceLanguage: string | "auto";
  targetLanguages: string[];
  outputFormats: Array<"srt" | "vtt">;
  qualityMode: "fast" | "high_quality";
}
```

## 11.4 Objet JobStatus

```ts
interface JobStatus {
  jobId: string;
  state:
    | "idle"
    | "probing"
    | "extracting_audio"
    | "chunking_audio"
    | "transcribing"
    | "post_processing"
    | "translating"
    | "completed"
    | "failed";
  progress: number;
  message?: string;
  errorCode?: string;
}
```

---

## 12. API locale recommandée

## 12.1 Endpoints backend

### `POST /api/videos/probe`
Entrée : fichier ou chemin local.

Sortie : métadonnées média.

### `POST /api/jobs`
Crée un job de traitement.

Body : `JobConfig`

Retour : `jobId`

### `GET /api/jobs/{jobId}`
Retourne l'état du job.

### `GET /api/jobs/{jobId}/preview`
Retourne les segments source et traduits disponibles.

### `GET /api/jobs/{jobId}/downloads`
Retourne la liste des fichiers exportables.

### `DELETE /api/jobs/{jobId}`
Supprime les artefacts du job.

### `GET /api/health`
Healthcheck local.

## 12.2 Suggestion architecture d'exécution

- création du job ;
- exécution asynchrone en arrière-plan local ;
- polling simple côté frontend toutes les 1 à 2 secondes en V1.

Pas besoin de WebSocket en V1 sauf si Claude Code veut le faire proprement sans surcomplexifier.

---

## 13. Intégration Groq

## 13.1 Principes

- toutes les clés et modèles passent par variables d'environnement ;
- aucun secret exposé dans le frontend ;
- prévoir des adaptateurs de fournisseur pour pouvoir changer de backend IA plus tard.

## 13.2 Variables d'environnement minimales

```env
GROQ_API_KEY=
GROQ_TRANSCRIPTION_MODEL=
GROQ_TRANSLATION_MODEL=
MAX_UPLOAD_MB=2048
MAX_API_AUDIO_CHUNK_MB=20
TEMP_DIR=
LOG_LEVEL=INFO
```

## 13.3 Abstraction recommandée

Créer deux interfaces :

- `SpeechToTextProvider`
- `SubtitleTranslationProvider`

Exemple conceptuel :

```python
class SpeechToTextProvider:
    async def transcribe(self, audio_path: str, source_language: str | None, quality_mode: str) -> list[dict]:
        ...

class SubtitleTranslationProvider:
    async def translate_segments(self, segments: list[dict], target_language: str) -> list[dict]:
        ...
```

L'implémentation Groq doit respecter ces interfaces.

---

## 14. Post-traitement sous-titres

## 14.1 Règles minimales

- pas de segment sans texte ;
- pas de fin avant début ;
- pas d'overlap volontaire ;
- ponctuation nettoyée ;
- découpage lisible ;
- pas de timecode négatif ;
- ordre strict.

## 14.2 Règles de lisibilité recommandées

- éviter plus de 2 lignes par segment si possible ;
- éviter les lignes trop longues ;
- éviter les segments d'une durée trop brève sans nécessité ;
- garder le sens avant le mot-à-mot.

## 14.3 Conversion de timecodes

Fonctions utilitaires à prévoir :

- `seconds_to_srt_timestamp`
- `seconds_to_vtt_timestamp`
- `segments_to_srt`
- `segments_to_vtt`

---

## 15. Gestion des erreurs

## 15.1 Cas à couvrir

- fichier introuvable ;
- format non supporté ;
- vidéo sans piste audio ;
- extraction audio échouée ;
- ffmpeg absent ;
- quota API atteint ;
- timeout API ;
- chunking échoué ;
- transcription partielle ;
- traduction partielle ;
- export impossible ;
- accès disque refusé.

## 15.2 Règle UX

Toujours afficher :

- ce qui a échoué ;
- à quelle étape ;
- ce que l'utilisateur peut faire ;
- si une partie des résultats reste téléchargeable.

Exemple :

- transcription source réussie ;
- traduction allemande échouée ;
- proposer quand même les exports source + autres langues réussies.

---

## 16. Logs et observabilité

Prévoir :

- logs structurés backend ;
- logs niveau `INFO`, `WARN`, `ERROR` ;
- identifiant de job ;
- timing des grandes étapes ;
- option debug pour conserver les fichiers intermédiaires.

---

## 17. Structure de projet recommandée

```text
subtitle-app/
  apps/
    desktop/
      src/
        components/
        pages/
        hooks/
        services/
        types/
      src-tauri/
  backend/
    app/
      api/
      core/
      models/
      services/
        media/
        stt/
        translation/
        subtitles/
        jobs/
      utils/
      main.py
    tests/
  docs/
    architecture.md
    api-contracts.md
  scripts/
  .env.example
  README.md
```

---

## 18. Stratégie de tests

## 18.1 Backend

- tests unitaires :
  - conversion timestamps ;
  - génération SRT/VTT ;
  - nettoyage segments ;
  - renommage fichiers ;
- tests d'intégration :
  - probe vidéo ;
  - extraction audio ;
  - chunking ;
  - pipeline transcription mockée ;
  - traduction mockée ;
- tests d'échec :
  - API indisponible ;
  - fichier corrompu.

## 18.2 Frontend

- import fichier ;
- sélection piste audio ;
- affichage états ;
- affichage erreurs ;
- affichage preview ;
- affichage liens de téléchargement.

## 18.3 E2E minimal

Un scénario complet avec mock API :

1. upload vidéo ;
2. config job ;
3. lancement ;
4. progression ;
5. résultat ;
6. téléchargement.

---

## 19. Dépendances clés recommandées

## 19.1 Frontend

- React
- TypeScript
- Vite
- TanStack Query ou équivalent
- Zod
- shadcn/ui ou équivalent

## 19.2 Backend

- FastAPI
- Uvicorn
- Pydantic
- httpx
- ffmpeg-python ou appels subprocess robustes
- python-multipart
- pytest
- anyio

### Note
Pour `ffmpeg`, des appels `subprocess` explicites peuvent être préférables à une abstraction trop magique afin de mieux contrôler les erreurs.

---

## 20. Contraintes d'implémentation importantes pour Claude Code

1. Ne pas coder une usine à gaz.
2. Prioriser une V1 fonctionnelle, lisible et testable.
3. Toute la logique métier doit être côté backend local.
4. Le frontend ne doit jamais connaître la clé API.
5. Le backend doit être organisé par services.
6. Le pipeline doit être relançable étape par étape si nécessaire.
7. Les formats de sous-titres doivent être générés par du code maison simple et testé.
8. Prévoir un provider pattern pour remplacer Groq plus tard.
9. Utiliser des types explicites partout.
10. Documenter l'installation locale de `ffmpeg`.

---

## 21. Critères d'acceptation V1

La V1 est considérée comme validée si les scénarios suivants fonctionnent :

### Scénario 1 — Transcription simple
- l'utilisateur charge une vidéo mp4 locale ;
- l'app détecte la piste audio ;
- l'app génère un `.srt` source valide ;
- l'utilisateur peut le télécharger.

### Scénario 2 — Traduction multi-langue
- l'utilisateur choisit FR + ES + DE ;
- l'app traduit les segments ;
- l'app génère les fichiers `.srt` correspondants ;
- les timecodes sont identiques à la version source.

### Scénario 3 — Vidéo avec plusieurs pistes audio
- l'app affiche les pistes ;
- l'utilisateur choisit la bonne ;
- la transcription correspond à cette piste.

### Scénario 4 — Fichier trop gros
- l'app déclenche le chunking ;
- les segments finaux restent chronologiquement corrects.

### Scénario 5 — Erreur partielle
- une traduction échoue ;
- l'app conserve les résultats déjà générés ;
- l'utilisateur peut quand même télécharger le reste.

---

## 22. Roadmap d'implémentation conseillée

### Phase 1
- initialisation du monorepo / projet ;
- shell desktop + backend local ;
- import vidéo ;
- probe vidéo ;
- extraction audio.

### Phase 2
- intégration transcription ;
- objet `SubtitleSegment` ;
- export `.srt` / `.vtt` source.

### Phase 3
- preview ;
- traduction segmentée ;
- export multi-langue.

### Phase 4
- gestion erreurs ;
- logs ;
- tests ;
- nettoyage ;
- documentation.

---

## 23. Prompt prêt à donner à Claude Code

Tu vas développer une application desktop de génération de sous-titres multilingues à partir de vidéos locales.

## Objectif produit
Créer une V1 propre, simple, robuste et maintenable permettant :
- d'importer une vidéo locale (`mp4`, `mov`, `mkv`, `avi`, `webm`) ;
- d'analyser la vidéo et ses pistes audio ;
- de sélectionner une piste audio si plusieurs sont présentes ;
- d'extraire l'audio avec `ffmpeg` ;
- de transcrire l'audio avec un provider cloud configurable ;
- de récupérer des segments horodatés ;
- de générer des sous-titres source aux formats `.srt` et `.vtt` ;
- de traduire les segments vers plusieurs langues cibles ;
- de générer un fichier `.srt` et `.vtt` par langue ;
- de télécharger les fichiers générés ;
- d'afficher l'avancement du traitement et les erreurs.

## Stack recommandée
- Desktop shell : Tauri
- Frontend : React + TypeScript
- Backend local : Python + FastAPI
- Média : ffmpeg / ffprobe
- Providers IA : architecture par interfaces, implémentation Groq en premier

## Contraintes techniques impératives
1. Ne jamais exposer la clé API côté frontend.
2. Toute la logique de traitement doit être dans le backend local Python.
3. Organiser le backend en services clairs : probe, extraction audio, chunking, transcription, traduction, export sous-titres, gestion de jobs, nettoyage.
4. Créer un provider pattern avec au minimum :
   - `SpeechToTextProvider`
   - `SubtitleTranslationProvider`
5. Prévoir des variables d'environnement pour la clé et les modèles.
6. Gérer les gros fichiers avec extraction audio puis chunking si nécessaire.
7. Lors de la transcription de chunks, réappliquer correctement les offsets temporels.
8. Les sous-titres traduits doivent conserver exactement les timecodes de la version source.
9. Générer `.srt` et `.vtt` via des fonctions utilitaires dédiées, testées.
10. Ne pas surcomplexifier l'UI en V1 : pas d'éditeur avancé, juste import, configuration, progression, preview simple, téléchargement.

## Fonctions attendues
### Backend
- endpoint de probe vidéo ;
- endpoint de création de job ;
- endpoint de statut de job ;
- endpoint de preview ;
- endpoint de liste des exports ;
- endpoint de suppression de job ;
- healthcheck.

### Frontend
- zone d'import ;
- affichage métadonnées ;
- sélection piste audio ;
- choix langue source auto/manuelle ;
- choix langues cibles ;
- choix format `.srt` / `.vtt` ;
- choix mode rapide / qualité ;
- bouton lancer ;
- barre ou indicateur de progression ;
- preview segments ;
- boutons de téléchargement.

## Data contracts minimaux
Implémente des types explicites pour :
- `SubtitleSegment`
- `TranslatedSubtitleSegment`
- `JobConfig`
- `JobStatus`

## Règles métier importantes
- supprimer les segments vides ;
- nettoyer les espaces et ponctuations aberrantes ;
- corriger les overlaps évidents ;
- garantir un ordre chronologique strict ;
- gérer les erreurs partielles sans perdre les résultats valides ;
- supprimer les temporaires à la fin, sauf mode debug.

## Qualité de code attendue
- architecture lisible ;
- typage strict ;
- fonctions petites et testables ;
- logs structurés ;
- documentation d'installation ;
- `.env.example` ;
- README clair ;
- tests unitaires sur timestamps et génération SRT/VTT.

## Plan d'exécution attendu
1. Initialiser la structure du projet.
2. Mettre en place le backend FastAPI.
3. Mettre en place le shell desktop et le frontend React.
4. Implémenter probe vidéo + extraction audio.
5. Implémenter le système de jobs.
6. Implémenter le provider STT.
7. Implémenter la génération SRT/VTT.
8. Implémenter la traduction segmentée.
9. Implémenter l'UI de progression, preview et téléchargement.
10. Ajouter tests, gestion d'erreurs et nettoyage.

## Attendu de ta réponse
Je veux que tu :
1. proposes l'arborescence complète du projet ;
2. génères le squelette initial des fichiers principaux ;
3. implémentes d'abord le backend et les utilitaires cœur ;
4. puis l'UI minimale ;
5. puis l'intégration Groq ;
6. puis les tests essentiels ;
7. et que tu expliques au fur et à mesure les choix structurants.

Ne pars pas sur une refonte imaginative de la stack. Respecte la V1 décrite, reste pragmatique, modulaire, testable et orienté livraison.

---

## 24. Prompt encore plus direct si tu veux qu'il code tout de suite

Code la V1 complète d'une application desktop de génération de sous-titres multilingues à partir de vidéos locales, avec :
- Tauri + React + TypeScript pour le frontend ;
- Python + FastAPI pour le backend local ;
- ffmpeg / ffprobe pour l'analyse média et l'extraction audio ;
- un provider cloud configurable pour la transcription et la traduction, avec Groq comme première implémentation ;
- export des sous-titres en `.srt` et `.vtt` ;
- traduction segment par segment avec conservation stricte des timecodes ;
- support des vidéos locales et des fichiers sur disque externe ;
- prise en charge des vidéos avec plusieurs pistes audio ;
- gestion de jobs avec statuts ;
- preview simple des segments ;
- téléchargement des exports ;
- nettoyage des fichiers temporaires.

Contraintes impératives :
- clé API uniquement côté backend ;
- code modulaire ;
- provider pattern ;
- typage strict ;
- tests minimum sur timestamps et export SRT/VTT ;
- pas d'éditeur avancé ;
- pas de cloud storage ;
- pas de compte utilisateur ;
- pas de sur-ingénierie.

Commence par l'arborescence, puis génère le squelette, puis implémente étape par étape le backend, puis le frontend, puis les tests, avec explication courte à chaque étape.

