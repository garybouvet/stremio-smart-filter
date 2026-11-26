"""Première installation sur un autre PC : déballe le paquet de données, puis construit l'index IMDb et la recherche par titre.

Usage (lancé par l'installeur) : python -m engine.setup_data <paquet.zip>
Le paquet vient de installeur/paquet.py : tmdb.db, extras.db et les dates de dernière relecture.
Les données IMDb ne sont pas dans le paquet (licence) : elles sont téléchargées ici, chez IMDb.
"""
import os, sys, zipfile
from . import imdb_index, names
from .imdb_index import DATA

EXPECTED = {'tmdb.db', 'extras.db'}


def unpack(archive, data=DATA):
    os.makedirs(data, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        members = set(z.namelist())
        if not EXPECTED <= members:
            raise ValueError('paquet de données incomplet')
        for name in members:
            if os.path.basename(name) != name:  # jamais de chemin : rien ne s'écrit hors de data/
                raise ValueError('paquet de données invalide')
            z.extract(name, data)
    return sorted(members)


def main(archive):
    print('Déballage des données…', flush=True)
    unpack(archive)
    print('Téléchargement des données IMDb et construction de l’index (quelques minutes)…', flush=True)
    imdb_index.download()
    imdb_index.build()
    print('Recherche par titre…', flush=True)
    print(names.build(), 'noms', flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
