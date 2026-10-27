"""Scientific figures for the geographical composition of the replay.

These plots consume the analytical CSV outputs; they do not change totals or
infer individual demographic characteristics from a polling section's location.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
import os
import tempfile
import unicodedata

# Headless rendering and a writable cache in managed cloud environments.
if not os.environ.get("MPLCONFIGDIR"):
    os.environ["MPLCONFIGDIR"] = str(Path(tempfile.gettempdir()) / "election-replay-mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

MAIN = "first_partial_totalization"
RECEIPT = "bu_received"
LULA = "#c62828"
FLAVIO = "#1565c0"
ROUND_COLORS = {"1": "#7952a8", "2": "#00897b"}
REGION_COLORS = {
    "Norte": "#2a9d8f", "Nordeste": "#d15b24", "Centro-Oeste": "#9b7b36",
    "Sudeste": "#386cb0", "Sul": "#7853a2", "Exterior": "#777777",
}
REGION_ORDER = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"]
NE_STATES = {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"}
CAPITAL_LABELS = {"capital": "Capitais (inclui DF)", "non_capital": "Demais municípios"}
SIZE_LABELS = {
    "<=10k": "Até 10 mil", "10k-50k": "10–50 mil", "50k-200k": "50–200 mil",
    "200k-1m": "200 mil–1 milhão", ">1m": "Mais de 1 milhão",
}
FOOTER = "Reconstrução retrospectiva aproximada • Hora TSE, sem conversão de fuso • Fontes: dois CSVs nacionais do repositório"


def _rows(output_dir: Path, name: str):
    with (output_dir / name).open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def _number(row, name):
    raw = row.get(name, "")
    return float(raw) if raw not in {"", None} else None


def _region(name):
    key = "".join(c for c in unicodedata.normalize("NFD", name.casefold()) if not unicodedata.combining(c))
    return {
        "norte": "Norte", "north": "Norte", "nordeste": "Nordeste", "northeast": "Nordeste",
        "centro-oeste": "Centro-Oeste", "center-west": "Centro-Oeste", "sudeste": "Sudeste",
        "southeast": "Sudeste", "sul": "Sul", "south": "Sul", "exterior": "Exterior",
        "overseas": "Exterior",
    }.get(key, name)


def _clock(value, _position=None):
    minute = int(round(value)) + 17 * 60
    days, within = divmod(minute, 24 * 60)
    label = f"{within // 60:02d}:{within % 60:02d}"
    return f"{label}\n(+{days} dia)" if days else label


def _percent(value, _position=None):
    return f"{value:.0f}%"


def _save(fig, output_dir: Path, stem: str, caption: str):
    folder = output_dir / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    fig.text(.02, .018, caption + "\n" + FOOTER, ha="left", va="bottom", fontsize=8, color="#536273")
    paths = []
    for suffix in ("png", "svg"):
        path = folder / f"{stem}.{suffix}"
        metadata = {"Date": None, "Creator": "Election replay analysis"} if suffix == "svg" else {"Software": "Election replay analysis"}
        fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white", metadata=metadata)
        paths.append(str(path.relative_to(output_dir)))
    plt.close(fig)
    return paths


def _finish(ax, percent=True):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dde3e9", linewidth=.7)
    ax.set_axisbelow(True)
    if percent:
        ax.yaxis.set_major_formatter(FuncFormatter(_percent))


def _regional_completion(output_dir):
    series = defaultdict(list)
    for row in _rows(output_dir, "geographic-minute.csv"):
        if row["source_timestamp"] == MAIN and row["dimension"] == "region":
            series[(row["turno"], _region(row["group"]))].append((float(row["minutes_after_1700"]), float(row["section_completion_percentage"])))
    coverage_at_1900 = defaultdict(lambda: [0, 0])
    for row in _rows(output_dir, "clock-completion.csv"):
        if row["source_timestamp"] == MAIN and row["dimension"] == "region" and row["clock"] == "19:00":
            coverage_at_1900[row["turno"]][0] += int(row["cumulative_sections"])
            coverage_at_1900[row["turno"]][1] += int(row["total_sections"])
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharey=True, sharex=True)
    last_minute = max((point[0] for points in series.values() for point in points), default=360)
    tick_end = (int(last_minute) // 120 + 1) * 120
    for turn, ax in zip(("1", "2"), axes):
        for region in REGION_ORDER:
            points = sorted(series.get((turn, region), []))
            if not points:
                continue
            x, y = zip(*points)
            ax.plot(x, y, label=region, color=REGION_COLORS[region], linewidth=2.6 if region == "Nordeste" else 1.6,
                    linestyle=":" if region == "Exterior" else "-", alpha=1 if region == "Nordeste" else .85)
        counted, total = coverage_at_1900[turn]
        if total:
            annotation = f"Às 19h: {100 * counted / total:.3f}% das seções nacionais".replace(".", ",")
            ax.text(.02, .98, annotation, transform=ax.transAxes, ha="left", va="top", fontsize=9,
                    bbox={"facecolor": "white", "edgecolor": "#dde3e9", "alpha": .95, "pad": 4})
        ax.set_title(f"{turn}º turno", fontweight="bold")
        ax.set_ylim(0, 102)
        ax.set_xlabel("Horário registrado (Hora TSE)")
        ax.xaxis.set_major_formatter(FuncFormatter(_clock))
        ax.set_xticks(range(0, tick_end + 1, 120))
        ax.set_xlim(0, tick_end + 10)
        _finish(ax)
    axes[0].set_ylabel("Seções da própria região contabilizadas")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .90), ncol=6, frameon=False, fontsize=9)
    fig.suptitle("Ritmo regional de contabilização das seções", fontsize=16, fontweight="bold")
    fig.subplots_adjust(top=.79, bottom=.24, wspace=.12)
    return _save(fig, output_dir, "regional-completion", "Referência: primeira totalização. Cada região tem seu próprio denominador; não é participação no total nacional.")


def _state_timing(output_dir, timing):
    rows = {(r["turno"], r["group"]): r for r in timing if r["source_timestamp"] == MAIN and r["dimension"] == "uf" and r["group"] != "ZZ"}
    states = sorted({uf for _, uf in rows}, key=lambda uf: float(rows.get(("1", uf), rows.get(("2", uf)))["t50_minutes"]))
    fig, ax = plt.subplots(figsize=(10.8, 11))
    for turn, shift, marker in [("1", -.16, "o"), ("2", .16, "s")]:
        for index, state in enumerate(states):
            row = rows.get((turn, state))
            if not row:
                continue
            low, median, high = (_number(row, c) for c in ("t10_minutes", "t50_minutes", "t90_minutes"))
            if median is None:
                continue
            ax.plot([low, high], [index + shift] * 2, color=ROUND_COLORS[turn], linewidth=2, alpha=.65)
            ax.scatter(median, index + shift, s=30, marker=marker, color=ROUND_COLORS[turn], zorder=3,
                       label=f"{turn}º turno" if index == 0 else None)
    ax.set_yticks(range(len(states)), states)
    for label in ax.get_yticklabels():
        if label.get_text() in NE_STATES:
            label.set_color("#b35416")
            label.set_fontweight("bold")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(_clock))
    ax.set_xlabel("Horário em que 10%, 50% e 90% das seções da própria UF foram contabilizadas")
    ax.set_title("Ritmo por UF: intervalo 10–90% e mediana (ponto)", fontsize=15, fontweight="bold", pad=18)
    ax.legend(loc="upper right", frameon=True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="#dde3e9", linewidth=.7)
    ax.set_axisbelow(True)
    fig.subplots_adjust(left=.09, right=.98, top=.94, bottom=.14)
    return _save(fig, output_dir, "state-timing", "Primeira totalização; UFs do Nordeste destacadas. Intervalos descrevem o conjunto das seções, não incerteza estatística.")


def _capital_size(output_dir, timing):
    rows = {(r["turno"], r["dimension"], r["group"]): r for r in timing if r["source_timestamp"] == MAIN}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.7), gridspec_kw={"width_ratios": [1, 1.4]})
    for ax, dimension, labels, title in [
        (axes[0], "capital_status", CAPITAL_LABELS, "Capitais × demais municípios"),
        (axes[1], "size_band", SIZE_LABELS, "Porte pelo eleitorado municipal"),
    ]:
        groups = list(labels)
        for turn, shift, marker in [("1", -.15, "o"), ("2", .15, "s")]:
            for index, group in enumerate(groups):
                row = rows.get((turn, dimension, group))
                if not row:
                    continue
                low, median, high = (_number(row, c) for c in ("t10_minutes", "t50_minutes", "t90_minutes"))
                if median is None:
                    continue
                ax.plot([low, high], [index + shift] * 2, color=ROUND_COLORS[turn], linewidth=2, alpha=.65)
                ax.scatter(median, index + shift, s=34, marker=marker, color=ROUND_COLORS[turn], zorder=3,
                           label=f"{turn}º turno" if index == 0 else None)
        ax.set_yticks(range(len(groups)), [labels[g] for g in groups])
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(FuncFormatter(_clock))
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("Hora TSE: intervalo 10–90%; ponto = 50%")
        ax.grid(axis="x", color="#dde3e9", linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .92), ncol=2, frameon=False)
    fig.suptitle("Geografia urbana e porte: distribuições do tempo das seções", fontsize=15, fontweight="bold")
    fig.subplots_adjust(left=.14, right=.98, top=.84, bottom=.25, wspace=.5)
    return _save(fig, output_dir, "capital-size-timing", "Brasil doméstico, primeira totalização. Porte = eleitores aptos, não população. Comparações agrupadas não isolam diferenças entre UFs.")


def _candidate_shares(output_dir, milestones):
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8), sharex=True)
    for turn, axrow in zip(("1", "2"), axes):
        for scope, ax in zip(("BR", "SP"), axrow):
            points = sorted([r for r in milestones if r["source_timestamp"] == MAIN and r["turno"] == turn and r["scope"] == scope], key=lambda r: float(r["actual_sections_percentage"]))
            for candidate, field, color in [("Lula (13)", "lula_percentage", LULA), ("Flávio Bolsonaro (22)", "flavio_percentage", FLAVIO)]:
                usable = [r for r in points if _number(r, field) is not None]
                ax.plot([float(r["actual_sections_percentage"]) for r in usable], [float(r[field]) for r in usable], color=color, marker="o", markersize=3.5, linewidth=2, label=candidate)
                if usable:
                    last = usable[-1]
                    other_field = "flavio_percentage" if field == "lula_percentage" else "lula_percentage"
                    other = _number(last, other_field)
                    offset = 7 if other is None or float(last[field]) >= other else -14
                    ax.annotate(f"{float(last[field]):.2f}%".replace(".", ","), (float(last["actual_sections_percentage"]), float(last[field])), xytext=(-3, offset), textcoords="offset points", ha="right", fontsize=9, color=color)
            ax.set_title(f"{'Brasil' if scope == 'BR' else 'Estado de São Paulo'} · {turn}º turno", fontweight="bold")
            ax.set_xlim(0, 102)
            ax.set_ylim(bottom=0)
            ax.xaxis.set_major_formatter(FuncFormatter(_percent))
            ax.set_ylabel("Votos nominais acumulados")
            _finish(ax)
    for ax in axes[-1]:
        ax.set_xlabel("Seções contabilizadas no próprio recorte")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper center", bbox_to_anchor=(.5, .945), frameon=False)
    fig.suptitle("Composição temporal do voto: Brasil e São Paulo", fontsize=16, fontweight="bold")
    fig.subplots_adjust(top=.85, bottom=.17, hspace=.32, wspace=.2)
    return _save(fig, output_dir, "candidate-shares", "Primeira totalização; pontos desde o marco de 5% (não série contínua), com empates incluídos. Denominador: todos os nominais; demais candidatos do 1º turno permanecem nele.")


def _northeast_composition(output_dir, milestones):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharey=True)
    for turn, ax in zip(("1", "2"), axes):
        final = None
        for source, style, label, color in [(MAIN, "-", "Primeira totalização", "#d15b24"), (RECEIPT, "--", "Recebimento do BU", "#555d69")]:
            rows = sorted([r for r in milestones if r["source_timestamp"] == source and r["turno"] == turn and r["scope"] == "BR"], key=lambda r: float(r["actual_sections_percentage"]))
            usable = [r for r in rows if _number(r, "ne_weight_percentage") is not None]
            ax.plot([float(r["actual_sections_percentage"]) for r in usable], [float(r["ne_weight_percentage"]) for r in usable], color=color, linestyle=style, marker="o", markersize=3.5, label=label)
            if usable:
                final = float(usable[-1]["ne_final_weight_percentage"])
        if final is not None:
            ax.axhline(final, color="#111111", linestyle=":", linewidth=1.2, label=f"Peso final: {final:.2f}%".replace(".", ","))
        ax.set_title(f"{turn}º turno", fontweight="bold")
        ax.set_xlabel("Seções nacionais contabilizadas")
        ax.set_xlim(0, 102)
        ax.xaxis.set_major_formatter(FuncFormatter(_percent))
        ax.legend(loc="best", fontsize=9, frameon=True)
        _finish(ax)
    axes[0].set_ylabel("Nordeste nos votos nominais já contabilizados")
    fig.suptitle("Quando o Nordeste ganha peso na apuração nacional?", fontsize=16, fontweight="bold")
    fig.subplots_adjust(top=.84, bottom=.24, wspace=.15)
    return _save(fig, output_dir, "northeast-composition", "Peso = nominais do Nordeste / nominais nacionais acumulados. A linha pontilhada é a participação final, não uma meta de velocidade.")


def _decomposition(output_dir):
    data = list(_rows(output_dir, "composition-decomposition.csv"))
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.2), sharex=True)
    targets = [10, 25, 50, 75, 90]
    for turn, axrow in zip(("1", "2"), axes):
        for scope, dimension, title, ax in [
            ("BR", "uf", "Brasil · entre UFs", axrow[0]),
            ("SP", "municipality", "São Paulo · entre municípios", axrow[1]),
        ]:
            rows = {int(float(r["requested_sections_percentage"])): r for r in data if r["source_timestamp"] == MAIN and r["turno"] == turn and r["scope"] == scope and r["dimension"] == dimension}
            available = [t for t in targets if t in rows]
            for delta, field, label, color in [(-.19, "composition_effect_pp", "Composição entre grupos", "#7952a8"), (.19, "within_group_effect_pp", "Ordenação dentro dos grupos", "#00897b")]:
                ax.bar([i+delta for i in range(len(available))], [float(rows[t][field]) for t in available], width=.36, color=color, label=label)
            ax.scatter(range(len(available)), [float(rows[t]["total_gap_pp"]) for t in available], color="#202a36", marker="D", s=25, label="Diferença total para o resultado final", zorder=3)
            ax.axhline(0, color="#333333", linewidth=.8)
            ax.set_xticks(range(len(available)), [f"{float(rows[t]['actual_sections_percentage']):.1f}%".replace(".", ",") for t in available])
            ax.set_title(f"{title} · {turn}º turno", fontweight="bold", fontsize=11)
            ax.set_ylabel("Diferença da parcela de Lula (p.p.)")
            _finish(ax, percent=False)
    for ax in axes[-1]:
        ax.set_xlabel("Progresso efetivo das seções no recorte")
    handles, labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=3, loc="upper center", bbox_to_anchor=(.5, .94), fontsize=9, frameon=False)
    fig.suptitle("Quanto do desvio inicial se associa à composição geográfica?", fontsize=15, fontweight="bold")
    fig.subplots_adjust(top=.83, bottom=.18, hspace=.3, wspace=.22)
    return _save(fig, output_dir, "composition-decomposition", "Identidade descritiva: desvio total = composição entre grupos + ordenação intragrupo; usa peso nominal e apoio final de cada grupo. Não estima causalidade.")


def generate_charts(output_dir: Path) -> list[str]:
    """Generate Portuguese PNG/SVG evidence figures from analytical CSVs."""
    output_dir = Path(output_dir)
    style = {
        "font.family": "DejaVu Sans", "font.size": 10, "axes.labelsize": 10,
        "axes.titlesize": 12, "figure.facecolor": "white", "axes.facecolor": "white",
        "svg.fonttype": "none", "svg.hashsalt": "election-replay-geography",
        "axes.edgecolor": "#536273", "axes.labelcolor": "#26364a",
        "text.color": "#26364a", "xtick.color": "#536273", "ytick.color": "#536273",
    }
    with plt.rc_context(style):
        timing = list(_rows(output_dir, "timing-summary.csv"))
        milestones = list(_rows(output_dir, "national-milestones.csv"))
        artifacts = []
        artifacts += _regional_completion(output_dir)
        artifacts += _state_timing(output_dir, timing)
        artifacts += _capital_size(output_dir, timing)
        artifacts += _candidate_shares(output_dir, milestones)
        artifacts += _northeast_composition(output_dir, milestones)
        artifacts += _decomposition(output_dir)
    return artifacts
