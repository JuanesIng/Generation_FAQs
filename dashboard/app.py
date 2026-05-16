import json
import os
from pathlib import Path

import streamlit as st

from faq_common import DATA_DIR

SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"
VALIDATIONS_PATH = DATA_DIR / "faq_validations.json"
VALIDATION_SERVICE_URL = os.getenv("VALIDATION_SERVICE_URL", "http://127.0.0.1:8004")

st.set_page_config(page_title="FAQ Review Panel", layout="wide")
st.title("Panel de revisión de FAQs")


@st.cache_data(ttl=30)
def load_suggestions():
    if not SUGGESTIONS_PATH.exists():
        return []
    with SUGGESTIONS_PATH.open() as f:
        return json.load(f).get("suggestions", [])


@st.cache_data(ttl=30)
def load_validations():
    if not VALIDATIONS_PATH.exists():
        return {}
    with VALIDATIONS_PATH.open() as f:
        return {v["suggestion_id"]: v for v in json.load(f)}


suggestions = load_suggestions()
validations = load_validations()

if not suggestions:
    st.warning("No hay sugerencias generadas todavía.")
    st.stop()

company_filter = st.selectbox(
    "Filtrar por empresa",
    ["Todas"] + sorted({s.get("company_name") or s["company_id"] for s in suggestions}),
)

filtered = [
    s for s in suggestions
    if company_filter == "Todas"
    or (s.get("company_name") or s["company_id"]) == company_filter
]

st.markdown(f"**{len(filtered)} sugerencias** · {len(validations)} revisadas")

for suggestion in filtered:
    sid = suggestion["id"]
    existing = validations.get(sid)
    status_label = f"✅ {existing['status']}" if existing else "⏳ Pendiente"

    with st.expander(f"{suggestion['question']}  —  {status_label}", expanded=not existing):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Pregunta**")
            st.write(suggestion["question"])
            st.markdown("**Respuesta sugerida**")
            st.write(suggestion["answer"])
        with col2:
            st.markdown("**Ejemplos reales**")
            for example in suggestion.get("support_examples", []):
                st.markdown(f"- {example}")
            st.caption(
                f"Empresa: {suggestion.get('company_name') or suggestion['company_id']} · "
                f"Cluster: {suggestion['cluster_size']} · Score: {suggestion['cluster_score']}"
            )

        if not existing:
            reviewer = st.text_input("Revisor", key=f"reviewer_{sid}")
            notes = st.text_area("Notas", key=f"notes_{sid}")
            col_a, col_b, col_c = st.columns(3)

            import requests

            def submit(status: str):
                if not reviewer:
                    st.warning("Ingresa tu nombre como revisor.")
                    return
                requests.post(
                    f"{VALIDATION_SERVICE_URL}/validate",
                    json={"suggestion_id": sid, "reviewer": reviewer, "status": status, "notes": notes},
                )
                st.cache_data.clear()
                st.rerun()

            with col_a:
                if st.button("✅ Aprobar", key=f"approve_{sid}"):
                    submit("approved")
            with col_b:
                if st.button("❌ Rechazar", key=f"reject_{sid}"):
                    submit("rejected")
            with col_c:
                if st.button("✏️ Cambios", key=f"changes_{sid}"):
                    submit("needs_changes")

        elif existing["status"] == "approved":
            if st.button("🚀 Promover a agent_faqs", key=f"promote_{sid}"):
                import requests
                response = requests.post(f"{VALIDATION_SERVICE_URL}/promote/{sid}")
                if response.ok:
                    st.success("FAQ promovida correctamente.")
                else:
                    st.error(f"Error: {response.json().get('detail')}")