// Version des fichiers de la page : chaque référence de euro-signal.html porte l'empreinte de son contenu (?v=…),
// pour qu'un téléphone ne mélange jamais une page récente avec un script ancien gardé en cache.
//   node tools/stamp.mjs          met à jour les empreintes
//   node tools/stamp.mjs --check  échoue si une empreinte n'est plus à jour (contrôle automatique)
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PAGE = path.join(ROOT, 'euro-signal.html');
const check = process.argv.includes('--check');
const html = fs.readFileSync(PAGE, 'utf8');
const stale = [];
const out = html.replace(
  /(<(?:script src|link rel="stylesheet" href)=")((?:app|euro_signal)\/[^"?]+)(?:\?v=([0-9a-f]+))?"/g,
  (m, pre, file, v) => {
    const full = path.join(ROOT, file);
    if (!fs.existsSync(full)) throw new Error('fichier introuvable : ' + file);
    const h = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex').slice(0, 10);
    if (h !== v) stale.push(file);
    return pre + file + '?v=' + h + '"';
  }
);
if (check) {
  if (stale.length) {
    console.error('Empreintes à mettre à jour (npm run stamp) : ' + stale.join(', '));
    process.exit(1);
  }
  console.log('Empreintes à jour');
} else {
  fs.writeFileSync(PAGE, out);
  console.log(stale.length ? 'Empreintes mises à jour : ' + stale.join(', ') : 'Empreintes déjà à jour');
}
