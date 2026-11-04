"""All Plotly figures. One palette, one hover rule, one axis per chart, and no chart sorted by a rate."""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from lib.rules import hover_text

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # fixed order, checked for colour vision deficiency
SCALE = "viridis_r"  # yellow at 0%, dark purple at 100%, with no grey anywhere, so a rate never looks like "too few" or "no isolates"
TOO_FEW = "#a9a8a2"
NO_ISOLATES = "#efeeea"
GRID = "#e4e3de"
PROVISIONAL = "rgba(120,120,110,0.13)"
PERCENT_AXIS = "% of sequenced isolates"


def _style(fig, title=None, height=420):
    fig.update_layout(title=title, height=height, margin=dict(l=10, r=10, t=56 if title else 16, b=10), paper_bgcolor="white",
                      plot_bgcolor="white", font=dict(size=13), hoverlabel=dict(align="left"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    fig.update_xaxes(showgrid=False, linecolor=GRID, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, automargin=True, title_standoff=8)
    return fig


def _rows_axis(fig, order, size=11):
    """Category rows in a fixed order, top to bottom, with no padding above the first row."""
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=list(order), range=[len(order) - 0.5, -0.5], showgrid=False, dtick=1, tickfont=dict(size=size))


def with_hover(rows, title_of):
    """Add a `hover` column to rate rows. `title_of` builds the bold first line from a row."""
    rows = rows.copy()
    rows["hover"] = [hover_text(title_of(r), r["rate"], r["n"], r["ci_low"], r["ci_high"], r["positives"], r["provisional"])
                     for r in rows.to_dict("records")]
    return rows


def world_map(rows, title=None, start_year=None):
    """Animated map with a year slider. Countries under the minimum and with no isolates look different from 0%."""
    rows = with_hover(rows, lambda r: f"{r['country']}, {int(r['year'])}")
    usable_years = sorted(rows.loc[rows["rate"].notna(), "year"].unique())
    if not usable_years:
        return None
    years = [int(y) for y in usable_years if y >= usable_years[-1] - 24]
    active = years.index(start_year) if start_year in years else len(years) - 1

    def traces(year):
        part = rows[rows["year"] == year]
        ok, few = part[part["rate"].notna()], part[part["rate"].isna()]
        return [go.Choropleth(locations=few["iso3"], z=[0] * len(few), text=few["hover"], hovertemplate="%{text}<extra></extra>",
                              colorscale=[[0, TOO_FEW], [1, TOO_FEW]], zmin=0, zmax=1, showscale=False, marker_line_color="white",
                              marker_line_width=0.4, name="Too few isolates"),
                go.Choropleth(locations=ok["iso3"], z=ok["rate"] * 100, text=ok["hover"], hovertemplate="%{text}<extra></extra>",
                              colorscale=SCALE, zmin=0, zmax=100, marker_line_color="white", marker_line_width=0.4,
                              colorbar=dict(title="%", thickness=12, len=0.7), name="Rate")]

    def step_label(year):
        return f"{year} p" if rows.loc[rows["year"] == year, "provisional"].any() else str(year)

    fig = go.Figure(data=traces(years[active]), frames=[go.Frame(data=traces(y), name=str(y)) for y in years])
    animate = dict(frame=dict(duration=700, redraw=True), transition=dict(duration=0), mode="immediate")
    fig.update_layout(
        updatemenus=[dict(type="buttons", direction="left", x=0, y=-0.02, xanchor="left", yanchor="top", showactive=False,
                          buttons=[dict(label="Play", method="animate", args=[None, {**animate, "fromcurrent": True}]),
                                   dict(label="Pause", method="animate", args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])],
        sliders=[dict(active=active, x=0.14, len=0.86, y=0, pad=dict(t=8), currentvalue=dict(prefix="Year: "),
                      steps=[dict(label=step_label(y), method="animate",
                                  args=[[str(y)], dict(frame=dict(duration=0, redraw=True), transition=dict(duration=0), mode="immediate")]) for y in years])])
    fig.update_geos(showframe=False, showcoastlines=False, showland=True, landcolor=NO_ISOLATES, showcountries=True,
                    countrycolor="white", projection_type="natural earth", lataxis_range=[-58, 85])
    _style(fig, title, 560)
    fig.update_layout(margin=dict(b=70))
    return fig


def _add_trend(fig, rows, name, color, row=None, col=None, showlegend=True):
    """One line with its Wilson band. Years under the minimum leave a gap rather than a joined line."""
    rows = rows.sort_values("year")
    ok = rows[rows["rate"].notna()]
    if ok.empty:
        return False
    place = dict(row=row, col=col) if row else {}
    groups = (ok["year"].diff() != 1).cumsum()
    for _, part in ok.groupby(groups):
        xs = list(part["year"]) + list(part["year"])[::-1]
        ys = list(part["ci_high"] * 100) + list(part["ci_low"] * 100)[::-1]
        single = len(part) == 1  # one usable year has no band to fill, so its interval is drawn as a short bar
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill=None if single else "toself", fillcolor=_rgba(color, 0.16), hoverinfo="skip",
                                 line=dict(width=5, color=_rgba(color, 0.3)) if single else dict(width=0), showlegend=False, legendgroup=name), **place)
    years = range(int(ok["year"].min()), int(ok["year"].max()) + 1)
    full = ok.set_index("year").reindex(years)
    fig.add_trace(go.Scatter(x=list(years), y=full["rate"] * 100, mode="lines+markers", name=name, legendgroup=name, showlegend=showlegend,
                             line=dict(color=color, width=2), marker=dict(size=8, color=color, line=dict(color="white", width=1)),
                             text=full["hover"], hovertemplate="%{text}<extra></extra>", connectgaps=False), **place)
    return True


def _rgba(color, alpha):
    return f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},{alpha})"


def trend(series, provisional_from, title=None, height=420, y_title=PERCENT_AXIS):
    """Trend lines from a {name: rows} dict, each with a `hover` column. Provisional years are shaded."""
    fig = go.Figure()
    drawn = [_add_trend(fig, rows, name, SERIES[i % len(SERIES)]) for i, (name, rows) in enumerate(series.items())]
    if not any(drawn):
        return None
    fig.add_vrect(x0=provisional_from - 0.5, x1=max(r["year"].max() for r in series.values() if len(r)) + 0.5, fillcolor=PROVISIONAL, line_width=0,
                  annotation_text="Provisional", annotation_position="top left", annotation_font_size=11)
    fig.update_yaxes(title=y_title, range=[0, 101])
    fig.update_xaxes(title="Collection year", dtick=2, tickformat="d")
    fig.update_layout(showlegend=sum(drawn) > 1, hovermode="closest")
    return _style(fig, title, height)


def trend_panels(panels, provisional_from, title=None):
    """Small multiples on the same axes, one panel per {name: rows}. Keeps the given order, which is by name."""
    names = list(panels)
    columns = min(3, len(names)) or 1
    lines = int(np.ceil(len(names) / columns))
    fig = make_subplots(rows=lines, cols=columns, shared_yaxes=True, shared_xaxes=True, subplot_titles=names, vertical_spacing=0.1, horizontal_spacing=0.03)
    drawn = False
    last = 0
    first = 9999
    for i, name in enumerate(names):
        row, col = i // columns + 1, i % columns + 1
        ok = _add_trend(fig, panels[name], name, SERIES[0], row, col, showlegend=False)
        drawn = drawn or ok
        if len(panels[name]):
            usable = panels[name][panels[name]["rate"].notna()]
            if len(usable):
                last, first = max(last, usable["year"].max()), min(first, usable["year"].min())
    if not drawn:
        return None
    fig.add_vrect(x0=provisional_from - 0.5, x1=max(last, provisional_from) + 0.5, fillcolor=PROVISIONAL, line_width=0, row="all", col="all")
    fig.update_yaxes(range=[0, 101], matches="y")
    fig.update_xaxes(range=[first - 0.5, max(last, provisional_from) + 0.5], tickformat="d")
    _style(fig, title, 300 * lines + 60)
    fig.update_yaxes(title=None)
    fig.update_yaxes(title=PERCENT_AXIS, col=1)
    fig.update_layout(showlegend=False, margin=dict(t=90 if title else 30))
    return fig


def rate_heatmap(rows, x, y, title=None, y_order=None, x_title=None, cell_px=22):
    """Heatmap of rates. Under the minimum is grey, and no isolates stays pale, so neither reads as 0%."""
    if rows.empty:
        return None
    xs = sorted(rows[x].unique())
    ys = y_order or sorted(rows[y].unique())
    z = rows.pivot_table(index=y, columns=x, values="rate", aggfunc="first", dropna=False).reindex(index=ys, columns=xs) * 100
    seen = rows.pivot_table(index=y, columns=x, values="n", aggfunc="first").reindex(index=ys, columns=xs)
    text = rows.pivot_table(index=y, columns=x, values="hover", aggfunc="first").reindex(index=ys, columns=xs)
    few = ((seen > 0) & z.isna()).astype(float).where((seen > 0) & z.isna())
    fig = go.Figure()
    fig.add_trace(go.Heatmap(x=xs, y=ys, z=few.values, text=text.values, hovertemplate="%{text}<extra></extra>", colorscale=[[0, TOO_FEW], [1, TOO_FEW]],
                             showscale=False, xgap=1, ygap=1, hoverongaps=False, name="Too few"))
    fig.add_trace(go.Heatmap(x=xs, y=ys, z=z.values, text=text.values, hovertemplate="%{text}<extra></extra>", colorscale=SCALE, zmin=0, zmax=100,
                             colorbar=dict(title="%", thickness=12, len=min(1, 300 / (cell_px * len(ys) + 90))), xgap=1, ygap=1, hoverongaps=False))
    fig.update_yaxes(autorange="reversed", type="category", showgrid=False, title=None)
    fig.update_xaxes(type="category", title=x_title, side="top", tickangle=-45 if x != "year" else None, dtick=None)
    _style(fig, title, max(260, cell_px * len(ys) + (200 if x != "year" else 130)))
    fig.update_layout(plot_bgcolor=NO_ISOLATES, margin=dict(t=170 if x != "year" else 90))
    return fig


def count_heatmap(rows, x, y, value, title=None, y_order=None):
    """Heatmap of isolate counts on a log colour scale, for the coverage view. These are counts, not rates."""
    if rows.empty:
        return None
    xs = sorted(rows[x].unique())
    ys = y_order or sorted(rows[y].unique())
    grid = rows.pivot_table(index=y, columns=x, values=value, aggfunc="sum").reindex(index=ys, columns=xs)
    fig = go.Figure(go.Heatmap(x=xs, y=ys, z=np.log10(grid.where(grid > 0)).values, customdata=grid.values, colorscale=SCALE, xgap=1, ygap=1, hoverongaps=False,
                               hovertemplate="<b>%{y}, %{x}</b><br>%{customdata:,} sequenced isolates<extra></extra>",
                               colorbar=dict(title="Isolates", thickness=12, tickvals=[0, 1, 2, 3, 4], ticktext=["1", "10", "100", "1,000", "10,000"], len=0.5)))
    fig.update_yaxes(autorange="reversed", type="category", showgrid=False)
    fig.update_xaxes(type="category", side="top", tickangle=-45)
    _style(fig, title, max(260, 20 * len(ys) + 130))
    fig.update_layout(plot_bgcolor=NO_ISOLATES, margin=dict(t=90))
    return fig


def count_bars(rows, x, y, title=None, y_title="Sequenced isolates", provisional_from=None, height=300):
    """Plain count bars by year. Counts carry no percentages."""
    if rows.empty:
        return None
    fig = go.Figure(go.Bar(x=rows[x], y=rows[y], marker_color=SERIES[0], hovertemplate=f"<b>%{{x}}</b><br>%{{y:,}} sequenced isolates<extra></extra>"))
    if provisional_from is not None and rows[x].max() >= provisional_from:
        fig.add_vrect(x0=provisional_from - 0.5, x1=rows[x].max() + 0.5, fillcolor=PROVISIONAL, line_width=0, annotation_text="Provisional",
                      annotation_position="top left", annotation_font_size=11)
    fig.update_yaxes(title=y_title)
    fig.update_xaxes(tickformat="d", title="Collection year")
    return _style(fig, title, height)


def spread_timeline(rows, title=None):
    """One row per country, earliest first. Established years lead, and record-only countries get their own marker."""
    if rows.empty:
        return None, 0
    rows = rows.copy()
    rows["order_year"] = rows["established_year"].fillna(9999)
    rows = rows.sort_values(["order_year", "first_year", "country"])
    established = rows[rows["established_year"].notna()]
    records = rows[rows["established_year"].isna()]
    low = established["established_year"].min() if len(established) else rows["first_year"].min()
    high = rows["first_year"].max() if established.empty else max(established["established_year"].max(), rows["first_year"].max())
    outside = int((rows["first_year"] < low - 1).sum())
    text = [f"<b>{r['country']}</b><br>Established {_year(r['established_year'])}<br>Earliest record {_year(r['first_year'])}<br>"
            f"{int(r['isolates']):,} sequenced isolates from {int(r['clusters']):,} clusters" for r in rows.to_dict("records")]
    rows["text"] = text
    fig = go.Figure()
    if len(established):
        fig.add_trace(go.Scatter(x=established["established_year"], y=established["country"], mode="markers", name="Established (3+ isolates, 2+ clusters)",
                                 marker=dict(size=9, color=SERIES[0], line=dict(color="white", width=1)), text=rows.loc[established.index, "text"], hovertemplate="%{text}<extra></extra>"))
    if len(records):
        fig.add_trace(go.Scatter(x=records["first_year"], y=records["country"], mode="markers", name="Record only, not established",
                                 marker=dict(size=9, color="white", line=dict(color=SERIES[1], width=2), symbol="diamond"), text=rows.loc[records.index, "text"], hovertemplate="%{text}<extra></extra>"))
    fig.update_xaxes(range=[low - 1, high + 1], tickformat="d", side="top", showgrid=True, gridcolor=GRID)
    _style(fig, title, max(300, 19 * len(rows) + 150))
    _rows_axis(fig, rows["country"])
    fig.update_layout(legend=dict(y=-0.01, yanchor="top", orientation="h"), margin=dict(t=70 if title else 40, b=40))
    return fig, outside


def _year(value):
    return "not reached" if value != value or value is None else str(int(value))


def countries_established(rows, title=None):
    """Cumulative number of countries with each gene family established. Rows: gene, established_year, country."""
    done = rows[rows["established_year"].notna()]
    if done.empty:
        return None
    fig = go.Figure()
    low, high = int(done["established_year"].min()), int(done["established_year"].max())
    for i, (gene, part) in enumerate(sorted(done.groupby("gene"))):
        counts = part.groupby("established_year")["country"].nunique().reindex(range(low, high + 1), fill_value=0).cumsum()
        fig.add_trace(go.Scatter(x=list(counts.index), y=counts.values, mode="lines", name=gene, line=dict(color=SERIES[i % len(SERIES)], width=2),
                                 hovertemplate=f"<b>{gene}</b>, %{{x}}<br>%{{y}} countries with it established<br>sequenced isolates only<extra></extra>"))
    fig.update_yaxes(title="Countries with the gene established", rangemode="tozero")
    fig.update_xaxes(title="Year", tickformat="d")
    return _style(fig, title, 400)


def early_warning_timeline(rows, title=None):
    """Country by year, with marker size showing the evidence. One colour; hover lists the genes."""
    if rows.empty:
        return None
    grouped = rows.groupby(["country", "established_year"]).agg(isolates=("recent_isolates", "sum"), clusters=("recent_clusters", "sum"), genes=("gene", lambda v: sorted(set(v)))).reset_index()
    grouped["text"] = [f"<b>{r['country']}, {int(r['established_year'])}</b><br>{len(r['genes'])} new: {', '.join(r['genes'][:6])}{' and more' if len(r['genes']) > 6 else ''}"
                       f"<br>{int(r['isolates']):,} recent sequenced isolates, {int(r['clusters']):,} clusters" for r in grouped.to_dict("records")]
    order = sorted(grouped["country"].unique())
    fig = go.Figure(go.Scatter(x=grouped["established_year"], y=grouped["country"], mode="markers", text=grouped["text"], hovertemplate="%{text}<extra></extra>",
                               marker=dict(size=np.sqrt(grouped["isolates"]), sizemode="diameter", sizeref=max(1, np.sqrt(grouped["isolates"].max()) / 28), sizemin=6,
                                           color=_rgba(SERIES[0], 0.75), line=dict(color="white", width=1))))
    years = sorted(grouped["established_year"].unique())
    fig.update_xaxes(tickvals=years, range=[years[0] - 0.5, years[-1] + 0.5], tickformat="d", side="top", gridcolor=GRID, showgrid=True)
    _style(fig, title, max(280, 20 * len(order) + 130))
    _rows_axis(fig, order)
    fig.update_layout(margin=dict(t=70 if title else 40))
    return fig


def cluster_bars(rows, title=None):
    """First to last year for each cluster, ordered by first year. Says "seen in", and shows no routes."""
    if rows.empty:
        return None
    rows = rows.sort_values(["first_year", "cluster_id"])
    rows = rows.assign(text=[f"<b>{r['cluster_id']}</b> ({r['organism_label']})<br>{int(r['first_year'])} to {int(r['last_year'])}<br>{int(r['isolates']):,} isolates, "
                             f"seen in {int(r['country_count'])} countries: {r['countries']}<br>Last-resort genes: {r['last_resort_genes'] or 'none'}" for r in rows.to_dict("records")])
    fig = go.Figure(go.Bar(y=rows["cluster_id"], x=rows["last_year"] - rows["first_year"] + 1, base=rows["first_year"] - 0.5, orientation="h", marker_color=SERIES[0],
                           text=rows["text"], textposition="none", hovertemplate="%{text}<extra></extra>"))
    fig.update_xaxes(tickformat="d", dtick=1, side="top", showgrid=True, gridcolor=GRID)
    _style(fig, title, max(260, 18 * len(rows) + 120))
    _rows_axis(fig, rows["cluster_id"], 10)
    fig.update_layout(margin=dict(t=70 if title else 40))
    return fig


def isolates_by_country(rows, title=None):
    """Isolate counts in name order. A count of what was sequenced, not a rate or a ranking."""
    if rows.empty:
        return None
    rows = rows.sort_values("country")
    fig = go.Figure(go.Bar(y=rows["country"], x=rows["isolates"], orientation="h", marker_color=SERIES[0],
                           hovertemplate="<b>%{y}</b><br>%{x:,} sequenced isolates with this gene<extra></extra>"))
    fig.update_xaxes(side="top", showgrid=True, gridcolor=GRID)
    _style(fig, title or "Sequenced isolates (count, not a rate)", max(260, 19 * len(rows) + 120))
    _rows_axis(fig, rows["country"])
    fig.update_layout(margin=dict(t=70))
    return fig


