"""Réglages : variables d'environnement, sinon fichier .env à la racine du projet (jamais commité)."""
import os

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')


def setting(name, default=None):
    if os.environ.get(name):
        return os.environ[name]
    if os.path.exists(ENV):
        for line in open(ENV, encoding='utf-8-sig', errors='replace'):  # BOM ou accents d'un autre encodage : sans plantage
            k, _, v = line.strip().partition('=')
            if k == name and v:
                return v.strip().strip('"')
    return default
