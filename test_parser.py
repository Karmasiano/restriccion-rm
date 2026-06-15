#!/usr/bin/env python3
"""Tests offline del parser y de la logica de decision (sin red)."""
import datetime as dt
import check_restriccion as cr

PREEMERGENCIA_HTML = """
<table><tbody><tr>
<td><strong>RESTRICCION VEHICULAR</strong></td>
<td>
<strong>Automoviles</strong><br>
&#8226; Con Sello Verde: 0-1<br>
&#8226; Sin Sello Verde: 0-1-2-3-4-5-6-7-8-9<br>
<strong>Transporte de carga (incluye camionetas)</strong><br>
(Interior Anillo Americo Vespucio)<br>
&#8226; Con Sello Verde: 4-5<br>
&#8226; Sin Sello Verde: 6-7-8-9-4-5
</td></tr></tbody></table>
"""
POST_PRE = {"title": {"rendered": "RM: Preemergencia Ambiental rige para este lunes 15 de junio"},
            "content": {"rendered": PREEMERGENCIA_HTML}, "link": "https://airerm.mma.gob.cl/x/"}
POST_ALERTA = {"title": {"rendered": "RM: Alerta Ambiental rige para este martes 26 de mayo"},
               "content": {"rendered": PREEMERGENCIA_HTML.replace("Con Sello Verde: 4-5", "Con Sello Verde: No hay")},
               "link": "https://airerm.mma.gob.cl/y/"}


def test_parser():
    ep = cr.parse_post(POST_PRE)
    assert ep["level"] == "PREEMERGENCIA"
    assert ep["carga_sv"] == "4-5"          # no confunde con el 0-1 de automoviles
    assert ep["date"].month == 6 and ep["date"].day == 15
    print("OK parser preemergencia ->", ep["carga_sv"])
    ep2 = cr.parse_post(POST_ALERTA)
    assert ep2["carga_sv"] is None           # 'No hay'
    print("OK parser alerta -> None")


def test_compute_status():
    today = dt.date(2026, 6, 15)
    ep = cr.parse_post(POST_PRE)
    ep["date"] = today                       # fija fecha al 'hoy' del test
    s = cr.compute_status(ep, today)
    assert s["restricted"] is True and s["carga_sello_verde"] == "4-5"
    print("OK compute_status restringido:", s["carga_sello_verde"])

    # Episodio viejo (no hoy ni manana) -> no restringe
    ep_old = cr.parse_post(POST_PRE); ep_old["date"] = today - dt.timedelta(days=5)
    assert cr.compute_status(ep_old, today)["restricted"] is False
    print("OK compute_status ignora episodio viejo")

    # Sin episodio -> no restringe
    assert cr.compute_status(None, today)["restricted"] is False
    print("OK compute_status sin episodio")


if __name__ == "__main__":
    test_parser()
    test_compute_status()
    print("\nTodos los tests pasaron.")
