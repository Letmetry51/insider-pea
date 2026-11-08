"""
Contrôles hors ligne des workflows GitHub (04/11/2026, stress test) :
- calcul du soir (.github/workflows/update-data.yml) : chaque étape qui exécute du code a son délai, et la somme des délais reste sous
  la limite du job (sinon un soir où Yahoo traîne, GitHub coupe le job avant le calcul : ni calcul ni email) ;
- publication (.github/actions/publish-site) : trois refus de GitHub font échouer l'étape (sinon page figée sans alerte, journal des
  alertes perdu et emails renvoyés le lendemain), un fichier de données illisible n'est jamais publié ;
- garde du soir (.github/workflows/watchdog.yml, 08/11/2026) : script exécuté tel quel avec un faux « gh » ; un calcul annulé dans
  la file d'attente des données (partagée avec Grain Signal) est relancé, même si la relance a elle aussi été annulée.
Sans dépendance (lecture ligne à ligne du YAML, Python seul).

  python tools/test_workflows.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results = []


def check(cond, name):
    results.append(("OK  " if cond else "ÉCHEC", name))


def job_steps(text, job):
    """Étapes d'un job : liste de dictionnaires {nom, timeout, run, uses} ; limite du job."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.rstrip() == "  " + job + ":")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i])), len(lines))
    job_timeout, steps, cur = None, [], None
    for l in lines[start + 1:end]:
        m = re.match(r"^    timeout-minutes:\s*(\d+)", l)
        if m:
            job_timeout = int(m.group(1))
        if re.match(r"^      - ", l):
            cur = {"name": "", "timeout": None, "run": False, "uses": ""}
            steps.append(cur)
        if cur is None:
            continue
        body = l[8:] if l.startswith("      - ") else l[8:] if l.startswith("        ") else None
        if body is None:
            continue
        m = re.match(r"(name|timeout-minutes|run|uses):\s*(.*)", body)
        if m:
            k, v = m.groups()
            if k == "name":
                cur["name"] = v.strip().strip('"')
            elif k == "timeout-minutes":
                cur["timeout"] = int(v)
            elif k == "run":
                cur["run"] = True
            else:
                cur["uses"] = v.strip()
    return job_timeout, steps


wf = (ROOT / ".github/workflows/update-data.yml").read_text(encoding="utf-8")
limit, steps = job_steps(wf, "update-data")
code = [s for s in steps if s["run"] or s["uses"].startswith("./")]
missing = [s["name"] for s in code if s["timeout"] is None]
check(not missing, "calcul du soir : un délai pour chaque étape qui exécute du code" + (f" (manque : {', '.join(missing)})" if missing else ""))
total = sum(s["timeout"] or 0 for s in steps)
check(limit is not None and total + 10 <= limit,
      f"calcul du soir : somme des délais des étapes ({total} min) sous la limite du job ({limit} min), 10 min de marge")
check(limit is not None and limit <= 360, f"calcul du soir : limite du job ({limit} min) dans le maximum de GitHub (360 min)")
pub = (ROOT / ".github/actions/publish-site/action.yml").read_text(encoding="utf-8")
check('[ "$ok" = 1 ] ||' in pub and "&& break; sleep 5; done" not in pub,
      "publication : trois refus de GitHub font échouer l'étape (jamais « Site publié » sans publication)")
check("continue-on-error: true" in pub.split("actions/upload-artifact")[0][-400:] + pub.split("actions/upload-artifact")[1][:120],
      "publication : la copie de secours en panne n'empêche pas la publication")
check("version publiée la veille gardée" in pub, "publication : un fichier de données illisible est remplacé par celui de la veille")
for f in sorted((ROOT / ".github/workflows").glob("*.yml")):
    t = f.read_text(encoding="utf-8")
    if "./.github/actions/publish-site" in t:
        check("persist-credentials: false" in t, f"{f.name} : jeton GitHub non laissé sur le disque (persist-credentials: false)")

# garde du soir (watchdog.yml) : script exécuté tel quel avec un faux « gh » (liste des calculs, relance, état des emails)
def watchdog(runs):
    """Lance le script de la garde ; runs : calculs du soir (créés après le départ prévu). → (code, sortie, relancé ?)"""
    import json
    import os
    import subprocess
    import tempfile
    import textwrap
    from datetime import datetime, timedelta, timezone
    text = (ROOT / ".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    script = textwrap.dedent(text.split("python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
    now = datetime.now(timezone.utc)
    d = now
    while not (d.weekday() < 5 and d.replace(hour=17, minute=37, second=0, microsecond=0) <= now):
        d -= timedelta(days=1)
    start = d.replace(hour=17, minute=37, second=0, microsecond=0)
    for k, r in enumerate(runs):
        r["createdAt"] = (start + timedelta(minutes=5 + k)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "gh"
        fake.write_text("#!/usr/bin/env python3\nimport os, sys\na = sys.argv[1:]\n"
                        "if a[:2] == ['run', 'list']: print(os.environ['FAKE_RUNS'])\n"
                        "elif a[:2] == ['workflow', 'run']: open(os.environ['FAKE_LOG'], 'a').write('relance\\n')\n"
                        "else: sys.exit(1)\n", encoding="utf-8")
        fake.chmod(0o755)
        logf = Path(tmp) / "log"
        env = dict(os.environ, PATH=tmp + os.pathsep + os.environ.get("PATH", ""), GH_TOKEN="x", REPO="o/r",
                   FAKE_RUNS=json.dumps(runs), FAKE_LOG=str(logf))
        p = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout + p.stderr, logf.exists()


def run_(event, conclusion, status="completed"):
    return {"event": event, "status": status, "conclusion": conclusion}


code, out, again = watchdog([run_("schedule", "cancelled")])
check(again and code == 0, "garde du soir : calcul du soir annulé dans la file d'attente → relancé")
code, out, again = watchdog([run_("schedule", "cancelled"), run_("workflow_dispatch", "cancelled")])
check(again and code == 0, "garde du soir : relance annulée elle aussi dans la file d'attente → relancé encore (au lieu de rien)")
code, out, again = watchdog([run_("schedule", "success")])
check(not again and code == 0, "garde du soir : calcul du soir réussi → rien à faire")
code, out, again = watchdog([run_("schedule", "failure"), run_("workflow_dispatch", "failure")])
check(not again and code == 1, "garde du soir : relance en échec → pas de nouvelle relance, problème signalé")
code, out, again = watchdog([run_("schedule", None, "in_progress")])
check(not again and code == 0, "garde du soir : calcul en cours → rien à faire")

if __name__ == "__main__":
    for st, name in results:
        print(f"{st} {name}")
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
