"""Robot du Live journée de SAGC'TOUT (dépôt public SAGC-live).

Le samedi (et le dimanche s'il y a des matchs), il lit la journée de Nationale 2 sur Rolskanet toutes les 15 s,
du quart d'heure avant le premier coup d'envoi jusqu'à la fin du dernier match, et dépose sa lecture au service
de SAGC'TOUT (POST /live/robot), que les téléphones relisent. Rolskanet refuse les appels venant de Cloudflare,
pas ceux de GitHub : c'est pour ça que ce robot existe.

Rien de secret ici : la clé du service est le secret LIVE_KEY du dépôt. Rien n'est gardé ni envoyé d'autre que ce
que l'appli affiche (ni licence ni date de naissance).

  python3 live.py                     le vrai passage (GitHub Actions)
  python3 live.py --essai 2026-10-24  une seule lecture de ce week-end, affichée, rien d'envoyé
"""
import datetime, http.cookiejar, json, os, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

RK = 'https://rolskanet.fr'
SERVICE = os.environ.get('LIVE_SERVICE') or 'https://sagc-notifs.clement-mora11.workers.dev'  # LIVE_SERVICE : un service d'essai
N2 = {'saison': 2027, 'competition_id': 1333, 'phase_id': 4298}  # saison 2026-27, Nationale 2, phase « Championnat de France N2 »
PARIS = ZoneInfo('Europe/Paris')
PAS = 15                                    # secondes entre deux lectures : le chrono s'arrête à chaque coup de sifflet (temps effectif)
BATTEMENT = 60                              # au plus une minute sans dépôt, même si rien n'a bougé (l'appli voit que le robot est là)
AVANT = datetime.timedelta(minutes=15)      # on commence un quart d'heure avant le premier coup d'envoi
TROP_TOT = datetime.timedelta(minutes=80)   # plus tôt que ça, on laisse un départ suivant prendre le relais (6 h maxi par passage)
DUREE_MAX = datetime.timedelta(hours=4)     # filet : un match oublié en « en cours » n'use pas le robot toute la nuit


class Rolskanet:
    """La page publique des rencontres donne le jeton et les cookies que Rolskanet demande à ses propres appels."""
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [('User-Agent', 'Mozilla/5.0 (sagc-live)')]
        page = self.op.open(RK + '/sportif/synthese/rencontres/RH', timeout=30).read().decode('utf-8', 'replace')
        m = re.search(r'name="csrf-token" content="([^"]+)"', page)
        if not m:
            raise RuntimeError('Rolskanet : jeton de page introuvable')
        self.csrf = m[1]

    def post(self, chemin, corps):
        req = urllib.request.Request(RK + chemin, data=json.dumps(corps).encode(), headers={
            'X-CSRF-TOKEN': self.csrf, 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'})
        return json.loads(self.op.open(req, timeout=30).read())


def rencontres(rk, du, au):
    corps = {**N2, 'equipe_term': None, 'discipline_code': 'RH', 'order_by': 'date_debut',
             'dates': {'start_date': du.strftime('%d/%m/%Y'), 'end_date': au.strftime('%d/%m/%Y')}}
    tout = []
    for page in range(1, 6):  # pages de 20 matchs : un week-end en tient 6
        d = rk.post(f'/sportif/synthese/ajax/liste_rencontres?page={page}', corps)
        bloc = d.get('data', d)
        lignes = bloc.get('data', []) if isinstance(bloc, dict) else bloc
        tout += lignes
        if not lignes or not ((d.get('links') or {}).get('next') or (bloc.get('next_page_url') if isinstance(bloc, dict) else None)):
            break
    return tout


def nom(p):
    return re.sub(r'\s+', ' ', str((p or {}).get('nom_complet') or '')).strip()[:60]


def detail(rk, rid, dom_id):
    """Un match commencé : les buts (buteur, numéro, seconde, gardien qui encaisse) et le chrono."""
    d = rk.post(f'/sportif/live/{rid}/ajax/ajax/init-data', {})
    buts = []
    for e in d.get('evenements') or []:
        if e.get('type') != 'BUT':
            continue
        b = e.get('buteur') or e.get('tireur') or {}
        buts.append({'t': int(e.get('temps') or 0), 'c': 'h' if (e.get('equipe') or {}).get('id') == dom_id else 'a',
                     'n': nom(b), 'num': str(b.get('numero') or '')[:4], 'gb': nom(e.get('gardien'))})
    ch, per = d.get('chronometre') or {}, d.get('periodes') or {}
    return {'debut': bool(d.get('estDebute')), 'pause': bool(d.get('estEnPause')), 'fin': bool(d.get('estTerminee')),
            'buts': sorted(buts, key=lambda b: b['t']),
            'chrono': {'debut': ch.get('reference_debut'), 'total': int(ch.get('milisecondes_total') or 0), 'pause': bool(ch.get('en_pause'))},
            'periodes': {'n': int(per.get('nombre') or 2), 'duree': int(per.get('duree') or 25)}}


def lire(rk, du, au, finis):
    """Les matchs du week-end ; le détail d'un match terminé n'est lu qu'une fois (finis)."""
    matchs = []
    for m in rencontres(rk, du, au):
        r, v = m.get('receveur') or {}, m.get('visiteur') or {}
        sc = {s['equipe_id']: s['score'] for s in m.get('score') or []}
        o = {'id': m['id'], 'j': int(m['tour']), 'quand': (m.get('infosRencontre') or {}).get('date_rencontre') or '',
             'dom': r.get('libelle_court') or '', 'ext': v.get('libelle_court') or '', 'etat': m.get('etat'),
             'forfait': bool(m.get('forfait')), 'score': [sc.get(r.get('id')), sc.get(v.get('id'))]}
        if o['etat'] in ('E', 'T'):
            if m['id'] not in finis:
                try:
                    finis[m['id']] = detail(rk, m['id'], r.get('id'))
                except Exception as e:  # un détail qui ne vient pas : le score s'affiche quand même
                    print(f'détail du match {m["id"]} : {e}')
            o.update(finis.get(m['id']) or {})
            if o['etat'] != 'T' or not o.get('fin'):
                finis.pop(m['id'], None)  # pas fini : relu au prochain passage
        matchs.append(o)
    return matchs


def coup_d_envoi(m):
    try:
        return datetime.datetime.strptime(m['quand'], '%d/%m/%Y %H:%M').replace(tzinfo=PARIS)
    except ValueError:
        return None


def deposer(du, au, matchs):
    req = urllib.request.Request(SERVICE + '/live/robot', data=json.dumps({
        'du': du.isoformat(), 'au': au.isoformat(), 'maj': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'matchs': matchs}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ['LIVE_KEY'], 'User-Agent': 'sagc-live'})
    urllib.request.urlopen(req, timeout=30).read()


def week_end(jour):
    sam = jour - datetime.timedelta(days=(jour.weekday() - 5) % 7) if jour.weekday() >= 5 else None
    return (sam, sam + datetime.timedelta(days=1)) if sam else (None, None)


def main():
    if '--essai' in sys.argv:
        du, au = week_end(datetime.date.fromisoformat(sys.argv[sys.argv.index('--essai') + 1]))
        print(json.dumps(lire(Rolskanet(), du, au, {}), ensure_ascii=False, indent=1))
        return
    maintenant = datetime.datetime.now(PARIS)
    du, au = week_end(maintenant.date())
    if not du:
        return print('Pas un week-end : rien à faire.')
    rk = Rolskanet()
    matchs = lire(rk, du, au, {})
    aujourdhui = [m for m in matchs if (coup_d_envoi(m) or maintenant).date() == maintenant.date() and m['etat'] not in ('R', 'I')]
    if not aujourdhui:
        return print(f'Pas de match de N2 le {maintenant.date()}.')
    if all(m['etat'] == 'T' for m in aujourdhui):
        deposer(du, au, matchs)
        return print('Tous les matchs du jour sont terminés : dernière lecture déposée.')
    debut = min(filter(None, map(coup_d_envoi, aujourdhui))) - AVANT
    if debut - maintenant > TROP_TOT:
        return print(f'Trop tôt (départ à {debut:%H:%M}) : un passage suivant prendra le relais.')
    if maintenant < debut:
        print(f'Attente jusqu\'à {debut:%H:%M}.')
        time.sleep((debut - maintenant).total_seconds())
    fin_max, finis, erreurs, dernier, depose = datetime.datetime.now(PARIS) + DUREE_MAX, {}, 0, None, 0.0
    ids = {m['id'] for m in aujourdhui}
    while datetime.datetime.now(PARIS) < fin_max:
        try:
            matchs = lire(rk, du, au, finis)
            # un dépôt seulement si quelque chose a bougé (but, arrêt, reprise du chrono), ou une fois par minute : peu d'écritures pour le service
            if matchs != dernier or time.time() - depose >= BATTEMENT:
                deposer(du, au, matchs)
                dernier, depose = matchs, time.time()
            erreurs = 0
            jour = [m for m in matchs if m['id'] in ids]
            print(f'{datetime.datetime.now(PARIS):%H:%M:%S} ' + ' | '.join(f"{m['dom'][:12]} {m['score'][0]}-{m['score'][1]} {m['etat'] or '-'}" for m in jour))
            if all(m['etat'] == 'T' for m in jour):
                return print('Tous les matchs du jour sont terminés.')
        except Exception as e:
            erreurs += 1
            print(f'Lecture ratée ({erreurs}) : {e}')
            if erreurs % 3 == 0:  # jeton expiré, cookie perdu : une nouvelle session Rolskanet
                try:
                    rk = Rolskanet()
                except Exception as e2:
                    print(f'Nouvelle session ratée : {e2}')
        time.sleep(PAS)
    print('Durée maximale atteinte.')


if __name__ == '__main__':
    main()
