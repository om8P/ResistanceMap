import streamlit as st

from lib import answers, data, ui

ui.header("Guided questions", "Fixed questions answered from the prepared tables, with no AI. Each one says when there is too little data.")
QUESTIONS = ["Is this resistance rising here?", "When did this gene reach each country?", "Is this a trend, or could it be one outbreak?",
             "What has newly appeared here recently?", "Is there enough data here?", "Are any drug classes unusually high here?"]
question = st.selectbox("Question", QUESTIONS, key="gq_question")
one, two, three = st.columns(3)

if question == QUESTIONS[0]:
    answer = answers.rising_question(ui.measure_picker("gq_measure", one), ui.organism_picker("gq_organism", two), ui.country_picker("gq_country", three))
elif question == QUESTIONS[1]:
    summary = data.load("gene_summary")
    options = sorted(set(summary["family"].dropna()))
    answer = answers.gene_question(one.selectbox("Gene family", options, index=options.index("blaNDM"), key="gq_gene"), ui.organism_picker("gq_gene_organism", two, include_all=True))
elif question == QUESTIONS[2]:
    answer = answers.outbreak_question(ui.measure_picker("gq_o_measure", one), ui.organism_picker("gq_o_organism", two), ui.country_picker("gq_o_country", three))
elif question == QUESTIONS[3]:
    answer = answers.new_genes_question(ui.country_picker("gq_n_country", one))
elif question == QUESTIONS[4]:
    answer = answers.enough_data_question(ui.organism_picker("gq_e_organism", one), ui.country_picker("gq_e_country", two))
else:
    answer = answers.hotspot_question(ui.organism_picker("gq_h_organism", one), ui.country_picker("gq_h_country", two))

if answer.status == "too_little":
    st.warning("Too little data for a firm answer.")
for line in answer.lines:
    st.markdown(line)
if answer.chart is not None:
    ui.chart(answer.chart)
if answer.table is not None:
    ui.table(answer.table)
