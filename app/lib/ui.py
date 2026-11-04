"""Shared page parts: pickers, view switches, notices and caveats."""
import streamlit as st

from lib import data
from lib.rules import NOTICE

SOURCE_LABEL = {"all": "All isolates", "clinical": "Clinical only", "environmental/other": "Environmental or other only"}
DEFAULT_ORGANISM = "Klebsiella"
DEFAULT_COUNTRY = "India"
CHART_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def header(title, intro=None):
    st.title(title)
    if intro:
        st.write(intro)
    st.caption(NOTICE)


def organism_picker(key, container=st, include_all=False):
    names = data.organisms()
    options = (["ALL"] if include_all else []) + list(names)
    labels = {"ALL": "All organisms", **names}
    default = options.index(DEFAULT_ORGANISM) if not include_all else 0
    return container.selectbox("Organism", options, index=default, format_func=labels.get, key=key)


def country_picker(key, container=st, label="Country"):
    options = data.countries()
    return container.selectbox(label, options, index=options.index(DEFAULT_COUNTRY), key=key)


def measure_picker(key, container=st):
    options = data.measures()
    return container.selectbox("Resistance measure", options, index=0, format_func=data.measure_label, key=key)


def view_controls(key, container=st, adjust=True, source=True):
    """Outbreak-adjusted and clinical switches, where tables exist for them. Returns (adjusted, source)."""
    adjusted, chosen = False, "all"
    if adjust:
        adjusted = container.toggle("Outbreak-adjusted", key=f"{key}_adjusted", help="Counts each outbreak cluster once per organism, country and year.")
    if source:
        chosen = container.selectbox("Isolate source", list(SOURCE_LABEL), format_func=SOURCE_LABEL.get, key=f"{key}_source")
    return adjusted, chosen


def view_note(adjusted, source):
    notes = []
    if adjusted:
        notes.append("Outbreak-adjusted: each cluster counts once per organism, country and year.")
    if source != "all":
        notes.append(f"{SOURCE_LABEL[source]}: isolates with no recorded type are left out. Pooled periods are not available in this view.")
    if notes:
        st.info(" ".join(notes))


def no_switch_note(what):
    st.caption(f"{what} has no clinical or environmental version, so the source switch does not apply here.")


def chart(fig, empty="Too little data to draw this chart. Every group is under the minimum of 30 isolates, or there are no rows."):
    if fig is None:
        st.warning(empty)
    else:
        st.plotly_chart(fig, width="stretch", theme=None, config=CHART_CONFIG)


def table(frame):
    """Scrolling table, or a fixed one where long sentences would be cut off."""
    has_long_text = any(frame[c].astype(str).str.len().max() > 40 for c in frame.columns if frame[c].dtype == object)
    if has_long_text and len(frame) <= 60:
        st.table(frame.set_index(frame.columns[0]))
    else:
        st.dataframe(frame, hide_index=True, width="stretch")


def legend_note():
    st.caption("Grey: under the minimum of 30 isolates, so no rate is shown. Palest shade: no isolates in the data. Neither means 0%. "
               "p on the slider, and shading on trends: provisional years, which are still incomplete.")


def caveats(organism=None, measure=None):
    """Caveats tied to what is on screen."""
    if organism == "Staphylococcus_aureus":
        shift = data.load_json("method_check")["share_shift"]["Staphylococcus_aureus"]
        st.warning(f"Staph aureus trends carry a method caveat: the mix of analysis methods shifted by {shift['largest_change_points']:.1f} points over "
                   f"{shift['first_year']} to {shift['last_year']}, and methods can give different results, so some of a trend may come from the method.")
    if measure and measure[1].startswith("CARBAPENEM"):
        st.caption("Carbapenem is slightly undercounted: genes with a class but no subclass, including 749 rows of bare blaKPC, are not matched.")
    if measure and measure[0] == "last_resort" and measure[2] == "any_excl_intrinsic":
        st.caption("Any mechanism except intrinsic includes point mutations and gene disruption, such as oprD loss in Pseudomonas.")


def near_universal_note():
    st.caption("Classes near 100% usually reflect intrinsic genes, such as fosA and blaSHV in Klebsiella. They are not new threats, and cannot flag as high.")
