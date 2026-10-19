#!/usr/bin/env bash
# Récupère les données du dernier calcul (branche « site ») dans data/, pour développer la page ou relancer un calcul en local.
# Les données ne sont pas dans la branche principale : elles appartiennent à leurs sources (voir README, « Sources de données »).
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch -q --depth 1 origin site
rm -rf data && git archive FETCH_HEAD data | tar -x
echo "Données du $(git log -1 --format=%cd --date=iso FETCH_HEAD) copiées dans data/"
