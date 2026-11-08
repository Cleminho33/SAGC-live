# SAGC-live

Robot du **Live journée** de SAGC'TOUT, l'appli de l'équipe de rink hockey du SA Gazinet Cestas (Nationale 2).

Le samedi (et le dimanche s'il y a des matchs), il lit la journée de N2 sur [Rolskanet](https://rolskanet.fr), du quart
d'heure avant le premier coup d'envoi jusqu'à la fin du dernier match : les scores toutes les 20 secondes, le détail d'un
match (buteurs, chrono) dès que son score bouge, sinon toutes les 40 s pour le nôtre et 2 min 30 pour les autres. Rolskanet
coupe au-delà d'environ 600 appels par heure ; le robot en fait environ 400. Il dépose sa lecture au service de l'appli,
que les téléphones relisent, avec l'heure où notre match s'est fini, et une dernière fois 16 min après (le service ouvre le vote 15 min après la fin).

- Plusieurs départs programmés l'après-midi (GitHub lance parfois ses robots en retard) ; un seul passage à la fois
- Aucun secret dans ce dépôt : la clé du service est le secret `LIVE_KEY`
- Rien d'autre n'est envoyé que ce que l'appli affiche (ni licence ni date de naissance)
- Essai sans rien envoyer : `python3 live.py --essai 2026-10-24`

Le code source est tenu dans le dépôt privé de Clément (`livrables/Rink/live-robot/`) et recopié ici.
