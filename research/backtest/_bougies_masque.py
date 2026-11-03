"""Lit le journal de « Recherche (à la demande) » lancé avec figures_bougies.py (gh run view <id> --log > bougies.log) et en tire
le masque des chandeliers par société et par semaine (texte base64 entre FIGURES-DEBUT et FIGURES-FIN) → bougies_mask.npz, lu par
_bougies_local.py."""
import base64
import io
import sys

import numpy as np

src = sys.argv[1] if len(sys.argv) > 1 else 'bougies.log'
parts = [line.split('B64:', 1)[1].strip() for line in open(src, encoding='utf-8', errors='replace') if 'B64:' in line]
z = np.load(io.BytesIO(base64.b64decode(''.join(parts))), allow_pickle=True)
np.savez_compressed('bougies_mask.npz', **{k: z[k] for k in z.files})
print({k: z[k].shape for k in z.files})
