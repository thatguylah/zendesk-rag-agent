"""
Streamlit UI for the live demo -- pick a ticket, see retrieval, generation,
and guardrail reasoning laid out visually. This is what you'd screen-share.

Run with: streamlit run app.py
"""
import streamlit as st

from src.agent import TicketResolutionAgent
from src.config import CONFIG
from src.guardrails import Gate
from src.ingest import build_index
from src.zendesk_client import ZendeskClient

st.set_page_config(page_title="Northwind Cloud -- Ticket Resolution Agent", layout="wide")

GATE_STYLE = {
    Gate.AUTO_SUGGEST: ("🟢", "Auto-suggest", "High confidence -- grounded in KB, ready for agent review."),
    Gate.NEEDS_REVIEW: ("🟡", "Needs review", "Partially grounded -- agent should verify before sending."),
    Gate.ESCALATE_LOW_GROUNDEDNESS: ("🔴", "Escalate", "KB context was retrieved, but the draft still drifted from it."),
    Gate.ESCALATE_NO_KB_MATCH: ("🔴", "Escalate", "No KB article was relevant enough to answer from -- refusing to guess."),
}


@st.cache_resource
def _setup():
    build_index()
    return ZendeskClient(), TicketResolutionAgent()


client, agent = _setup()

st.title("🎫 Northwind Cloud -- AI Ticket Resolution Agent")
st.caption(
    f"RAG pipeline demo · LLM provider: **{CONFIG.llm_provider}** · "
    f"Embeddings: **{CONFIG.embedding_backend}** · "
    f"Zendesk source: **{'live account' if client.is_live else 'sample data'}**"
)

with st.sidebar:
    st.header("Ticket queue")
    tickets = client.list_tickets()
    ticket_labels = {f"#{t.id} -- {t.subject}": t for t in tickets}
    selected_label = st.radio("Select a ticket", list(ticket_labels.keys()), label_visibility="collapsed")
    selected_ticket = ticket_labels[selected_label]

    st.divider()
    st.subheader("How this works")
    st.markdown(
        "1. **Retrieve** top-k KB articles by embedding similarity\n"
        "2. **Guardrail** -- refuse to generate if nothing retrieved clears the confidence floor\n"
        "3. **Generate** a grounded draft, citing article IDs\n"
        "4. **Guardrail** -- redact any pasted credentials, score groundedness independently of the model's own claims\n"
        "5. **Gate** the result: auto-suggest / needs review / escalate to a human"
    )

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Ticket")
    st.markdown(f"**Subject:** {selected_ticket.subject}")
    st.markdown(f"**Requester:** {selected_ticket.requester}")
    st.markdown(f"**Priority:** {selected_ticket.priority}")
    st.info(selected_ticket.description)

    run = st.button("▶ Resolve with AI agent", type="primary", use_container_width=True)

with col2:
    st.subheader("Agent output")
    if run:
        with st.spinner("Retrieving KB context and generating draft..."):
            result = agent.resolve(selected_ticket)

        icon, label, explanation = GATE_STYLE[result.gate]
        st.markdown(f"### {icon} {label}")
        st.caption(explanation)

        if result.notes:
            for note in result.notes:
                st.warning(note)

        if result.retrieval_sufficient:
            st.metric("Groundedness score", f"{result.groundedness:.0%}")
            st.progress(result.groundedness)

            st.markdown("**Draft reply (internal note, not sent to customer):**")
            st.success(result.draft_reply)

            st.markdown(f"**Cited KB articles:** {', '.join(result.cited_kb_ids) or 'none'}")

            if result.unsupported_sentences:
                with st.expander("⚠️ Sentences the groundedness check could NOT verify against retrieved KB text"):
                    for s in result.unsupported_sentences:
                        st.write(f"- {s}")
        else:
            st.error("No draft generated -- retrieval confidence was too low. Routed to a human agent.")

        with st.expander("Retrieved KB context (what the model was allowed to use)"):
            for c in result.retrieved_chunks:
                st.markdown(f"**[{c.kb_id}] {c.title}** -- similarity {c.similarity:.2f}")
                st.text(c.text[:400] + ("..." if len(c.text) > 400 else ""))
                st.divider()
    else:
        st.write("Click **Resolve with AI agent** to run the pipeline on this ticket.")
