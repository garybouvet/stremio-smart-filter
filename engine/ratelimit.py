"""Limite de requêtes par adresse IP (fenêtre glissante), pour le moteur exposé sur Internet."""
import collections, threading, time

_hits = collections.defaultdict(collections.deque)
_lock = threading.Lock()


def allow(ip, limit=120, window=60.0, now=None):
    """True si l'IP a fait moins de `limit` requêtes dans les `window` dernières secondes."""
    now = time.monotonic() if now is None else now
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > 10000:  # shortcut: purge brutale si trop d'IP différentes, remplacer par un LRU si besoin
            _hits.clear()
        return True
