// Contrôle du code (npm run lint) : erreurs réelles seulement (variable inconnue, doublon, code inatteignable…), pas de style.
// Le style est fixé par Prettier (npm run format).
import fs from 'node:fs';
import globals from 'globals';

// Les scripts de app/ sont des scripts classiques chargés dans l'ordre par euro-signal.html : les fonctions et variables
// déclarées au premier niveau d'un fichier sont visibles des autres. On les déclare donc comme globales partagées.
const appFiles = fs.readdirSync('app').filter((f) => f.endsWith('.js'));
const shared = {};
for (const f of appFiles) {
  const src = fs.readFileSync('app/' + f, 'utf8');
  for (const m of src.matchAll(/^function ([A-Za-z_$][\w$]*)/gm)) shared[m[1]] = 'readonly';
  for (const m of src.matchAll(/^var ([^;]+)/gm)) {
    for (const v of m[1].matchAll(/(?:^|,\s*)([A-Za-z_$][\w$]*)\s*(?==|,|$)/g)) shared[v[1]] = 'writable';
  }
}

const bugs = {
  'no-undef': 'error',
  'no-redeclare': 'error',
  'no-dupe-keys': 'error',
  'no-dupe-args': 'error',
  'no-dupe-else-if': 'error',
  'no-duplicate-case': 'error',
  'no-unreachable': 'error',
  'no-func-assign': 'error',
  'no-const-assign': 'error',
  'no-self-assign': 'error',
  'no-unsafe-finally': 'error',
  'no-unsafe-negation': 'error',
  'no-obj-calls': 'error',
  'use-isnan': 'error',
  'valid-typeof': 'error',
  'getter-return': 'error',
  'no-unexpected-multiline': 'error',
  'no-unused-vars': ['warn', { vars: 'local', args: 'none', caughtErrors: 'none' }],
};

export default [
  { ignores: ['data/**', 'node_modules/**', 'research/**'] },
  {
    files: ['euro_signal/core.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'script', globals: { ...globals.browser, ...globals.node } },
    rules: bugs,
  },
  {
    files: ['app/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: { ...globals.browser, ES: 'readonly', ...shared },
    },
    rules: { ...bugs, 'no-redeclare': ['error', { builtinGlobals: false }] },
  },
  {
    files: ['sw.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'script', globals: { ...globals.serviceworker } },
    rules: bugs,
  },
  {
    files: ['euro_signal/**/*.mjs', 'tools/**/*.mjs', 'eslint.config.mjs'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'module', globals: { ...globals.node } },
    rules: bugs,
  },
  {
    // les fonctions passées à page.evaluate() s'exécutent dans le navigateur
    files: ['euro_signal/ui_check.mjs', 'tools/inject_check.mjs'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  {
    files: ['euro_signal/tests.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'commonjs', globals: { ...globals.node } },
    rules: bugs,
  },
];
