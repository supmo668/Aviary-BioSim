# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "pyyaml", "pandas", "altair", "pyarrow"]
# ///
# Run:  uv run --with marimo --with pyyaml --with pandas --with altair --with pyarrow \
#         marimo run dashboard/v2r_dashboard.py
# pyarrow is not imported directly — altair uses it to serialise data frames, and
# without it every chart falls back to CSV with a warning.
import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import pandas as pd
    import yaml

    return Path, alt, mo, pd, yaml


@app.cell
def _(Path, mo):
    v2r_path = mo.ui.text(
        value=str(Path.cwd() / ".v2r"),
        label="Run directory",
        full_width=True,
    )
    v2r_path
    return (v2r_path,)


@app.cell
def _(Path, v2r_path, yaml):
    v2r = Path(v2r_path.value)
    register = yaml.safe_load((v2r / "register.yaml").read_text())
    records = [
        yaml.safe_load(p.read_text())
        for p in sorted(v2r.glob("run-record-*.yaml"), key=lambda p: int(p.stem.split("-")[-1]))
    ]
    units = register["units"]
    return records, register, units, v2r


@app.cell
def _(mo, records, register, units):
    STATE_COLOR = {
        "closed": "#2f855a",
        "parked": "#b7791f",
        "claimed": "#2b6cb0",
        "open": "#718096",
    }

    def tile(label, value, sub, color="#1a202c"):
        return f"""
        <div style="flex:1;min-width:150px;padding:14px 16px;border:1px solid #e2e8f0;
                    border-radius:10px;background:#fff">
          <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;
                      color:#718096">{label}</div>
          <div style="font-size:30px;font-weight:650;color:{color};line-height:1.15">{value}</div>
          <div style="font-size:12px;color:#718096">{sub}</div>
        </div>"""

    _counts = {_s: sum(1 for _u in units if _u["state"] == _s) for _s in STATE_COLOR}
    _n = len(units)
    _drains = len(records)
    _pin = register["run"]["instinct_pin"] or "none (empty instinct store)"
    _reqs = len({_u["satisfies"] for _u in units})

    mo.md(f"""
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px">
{tile("Build units", _n, f"across {_reqs} standing requirements")}
{tile("Closed", _counts["closed"], "sealed test passed, committed", STATE_COLOR["closed"])}
{tile("Parked", _counts["parked"], "attempt preserved on a branch", STATE_COLOR["parked"])}
{tile("Drains", _drains, "each under one pinned builder")}
</div>

**Instinct pin** &nbsp;`{_pin}` &nbsp;·&nbsp; every drain is attributable to exactly one builder
""")
    return (STATE_COLOR,)


@app.cell
def _(mo):
    mo.md(
        """
    ## Does it actually get better?

    Each drain retries **only** what parked, under a fresh instinct pin. The loop stops
    itself when a drain closes nothing new — that is the termination condition, not a
    timeout.
    """
    )
    return


@app.cell
def _(alt, mo, pd, records, units):
    _n_units = len(units)
    _rows = []
    for _rec in records:
        _rows.append({"drain": f"drain {_rec['drain']}", "state": "closed",
                      "count": len(_rec["closed"])})
        _rows.append({"drain": f"drain {_rec['drain']}", "state": "parked",
                      "count": len(_rec["parked"])})
        _rows.append({"drain": f"drain {_rec['drain']}", "state": "not yet attempted",
                      "count": _n_units - len(_rec["closed"]) - len(_rec["parked"])})
    progress = pd.DataFrame(_rows)

    chart = (
        alt.Chart(progress)
        .mark_bar(size=46)
        .encode(
            y=alt.Y("drain:N", title=None, sort=None),
            x=alt.X("count:Q", title="build units", stack="zero"),
            color=alt.Color(
                "state:N",
                scale=alt.Scale(
                    domain=["closed", "parked", "not yet attempted"],
                    range=["#2f855a", "#b7791f", "#e2e8f0"],
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=["drain", "state", "count"],
        )
        .properties(height=190, width="container")
    )

    _deltas = []
    for _prev, _cur in zip(records, records[1:]):
        _gained = len(_cur["closed"]) - len(_prev["closed"])
        _deltas.append(
            f"- **drain {_prev['drain']} → {_cur['drain']}**: "
            + (f"recovered **{_gained}** parked unit{'s' if _gained != 1 else ''}"
               if _gained else "**closed nothing new — loop terminates**")
        )

    mo.vstack([mo.ui.altair_chart(chart, chart_selection=False), mo.md("\n".join(_deltas))])
    return


@app.cell
def _(mo):
    mo.md(
        """
    ## Every unit, and what it cost

    `attempts` is how many times an implementer tried before the gate accepted or the
    budget ran out. The gate re-runs the sealed test itself — no agent can assert a close.
    """
    )
    return


@app.cell
def _(mo, pd, units):
    table = pd.DataFrame(
        [
            {
                "unit": _u["id"],
                "satisfies": _u["satisfies"],
                "state": _u["state"],
                "attempts": _u["attempts"],
                "behaviour": _u["statement"],
            }
            for _u in units
        ]
    )
    mo.ui.table(table, selection=None, page_size=25)
    return


@app.cell
def _(mo, units):
    _reqmap = {}
    for _u in units:
        _r = _reqmap.setdefault(_u["satisfies"], {"closed": 0, "total": 0})
        _r["total"] += 1
        _r["closed"] += _u["state"] == "closed"

    _bars = []
    for _req in sorted(_reqmap):
        _c, _t = _reqmap[_req]["closed"], _reqmap[_req]["total"]
        _pct = round(100 * _c / _t)
        _bars.append(
            f"""<div style="display:flex;align-items:center;gap:10px;margin:5px 0">
              <code style="width:38px;color:#1a202c">{_req}</code>
              <div style="flex:1;height:9px;background:#edf2f7;border-radius:5px;overflow:hidden">
                <div style="width:{_pct}%;height:100%;
                            background:{'#2f855a' if _pct == 100 else '#b7791f'}"></div>
              </div>
              <span style="font-size:12px;color:#718096;width:78px">{_c}/{_t} closed</span>
            </div>"""
        )

    mo.md(
        "## Standing requirements\n\n"
        "A requirement is **never closed** — it is enforced for the life of the project. "
        "These bars show how much of each one currently has a build unit behind it.\n\n"
        + "".join(_bars)
    )
    return


@app.cell
def _(Path, mo, units, v2r):
    _parked = [_u for _u in units if _u["state"] == "parked"]
    if _parked:
        _blocks = []
        for _u in _parked:
            _ev = Path(_u["evidence"]) if _u["evidence"] else None
            _eff = (v2r.parent / _ev) if _ev and not _ev.is_absolute() else _ev
            _body = _eff.read_text().strip() if _eff and _eff.exists() else "(evidence not found)"
            _blocks.append(
                f"**{_u['id']}** · `{_u['park_branch']}` · {_u['attempts']} attempts\n\n"
                f"> {_u['statement']}\n\n```\n{_body}\n```"
            )
        out = mo.md(
            "## Parked — waiting on a human\n\nThe attempt is preserved on a branch and "
            "the tree was restored, so every commit on the branch stays green.\n\n"
            + "\n\n".join(_blocks)
        )
    else:
        out = mo.md("## Parked\n\nNothing parked — the register drained completely.")
    out
    return


if __name__ == "__main__":
    app.run()
