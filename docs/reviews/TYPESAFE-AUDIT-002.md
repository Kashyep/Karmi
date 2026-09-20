# KARMI — TYPESAFE AI SYSTEM ARCHITECTURE AUDIT

**Purpose:** This document audits the current heuristic and mock-based AI implementation in Karmi (`daily_agent`) and provides a concrete, rigorous blueprint for replacing brittle code with TypeSafe AI primitives.

## 1. Executive Summary

Karmi’s current AI interfaces (specifically `fake_generate` and `build_note_context` in `services.py`) rely on naive, brittle heuristics. Text matching (`"remember" in lowered`) and chronological truncation limit the system's ability to act as a robust, capable daily assistant. 

By integrating **TypeSafe AI**, we can replace these heuristics with **System One** judgments—fast, typed, and structured probabilities that inject "programmable common sense" directly into the Python workflow. This approach shifts semantic understanding away from monolith prompt engineering to discrete, verifiable programming primitives (`Choice`, `Score`, `Noul`).

---

## 2. Semantic Routing & Speculative Fan-out (`Choice`)

### Current Flaw
`fake_generate` determines routing and behavior using hardcoded exact string matching:
```python
if lowered.startswith("remember") and not context.text:
    ...
if "my notes" in lowered or "remember" in lowered:
    ...
```
This fails on semantic variations ("I need you to memorize...", "Recall that...").

### TypeSafe Intervention: `Choice` Primitive
We can replace the routing step with a typed `Choice` judgment to determine the user's semantic intent before dispatching to specific handlers.

*   **Primitive**: `Choice`
*   **State**: `{ "user_message": body.text, "recent_interactions": [...] }`
*   **Question**: "What is the primary action the user is asking the assistant to take?"
*   **Criteria**: 
    *   `query_memory`: "The user is asking to retrieve, search, or recall saved facts."
    *   `store_memory`: "The user is providing a new fact or note to be remembered."
    *   `create_task`: "The user is instructing the assistant to create a to-do, task, or reminder."
    *   `general_draft`: "The user is asking for text generation, drafting, or general chat."
*   **Execution Strategy**: By using `Choice`, the Python backend can switch safely:
    ```python
    intent = await typesafe.choice(state=state, options=criteria)
    if intent.id == "query_memory":
        return await handle_memory_query(text, session)
    elif intent.id == "create_task":
        return await handle_task_creation(text, session)
    ```

---

## 3. Precision Memory Management (`Score`)

### Current Flaw
In `api.py` / `services.py`, `build_note_context` ranks and packs memory blindly based on recency (`order_by(Note.updated_at.desc())`), truncating when it hits `max_tokens`.
```python
for note in notes:
    if used + estimate > max_tokens:
        omitted.append(note.id)
        continue
```
This forces the LLM to read irrelevant context while dropping older, potentially critical context needed for the query.

### TypeSafe Intervention: `Score` Primitive
Instead of chronological packing, we can score notes for relevance to the active query in parallel.

*   **Primitive**: `Score`
*   **State**: `{ "user_query": body.text, "candidate_note": note.content }`
*   **Question**: "How relevant is this saved note to fulfilling the user's current query?"
*   **Criteria (Levels)**:
    *   `0 (Irrelevant)`: "The note contains nothing related to the entities, topics, or intent of the user's query."
    *   `1 (Tangential)`: "The note shares themes or entities, but does not directly answer the query."
    *   `2 (Directly Relevant)`: "The note contains specific facts, dates, or constraints necessary to fulfill the query."
*   **Execution Strategy**: 
    Run `Score` asynchronously across the candidate note pool. Pack the context window strictly in descending order of the TypeSafe score. This ensures the generator only sees the highest-quality context, saving tokens (and budget) while eliminating hallucinations.

---

## 4. Extraction Verification & Guardrails (`Noul`)

### Current Flaw
`create_task` and `create_reminder` currently rely on structured JSON input via the API, shifting the burden of natural language extraction entirely to the client or assuming perfect upstream LLM extraction.

### TypeSafe Intervention: `Noul` Primitive
When natural language extraction pipelines (e.g., extracting a `due_at_utc` from "remind me to call John on Friday") produce a candidate JSON structure, we must verify it against the source text before committing to PostgreSQL.

*   **Primitive**: `Noul`
*   **State**: 
    ```json
    {
      "source_text": "remind me to call John on Friday",
      "extracted_task": {"title": "Call John", "due_at_utc": "2026-09-25T12:00:00Z"}
    }
    ```
*   **Question**: "Does the extracted task accurately reflect all constraints in the source text without inventing unsupported details?"
*   **Execution Strategy**: 
    If `Noul` returns a high probability of YES (>0.85), commit to DB. If probability is low, loop back to a repair step or escalate to `Outcome.REPAIR`.

---

## 5. Action Selection & Outcome Determination (`Choice`)

### Current Flaw
`MessageView` requires an `Outcome` enumeration (`ACCEPT`, `REPAIR`, `ESCALATE`, `ASK_USER`, `SAFE_STOP`, `DEFERRED`). `fake_generate` hardcodes these outcomes arbitrarily. 

### TypeSafe Intervention: `Choice`
We can decouple the generation of the response text from the determination of the system state.

*   **Primitive**: `Choice`
*   **State**: `{ "user_message": body.text, "draft_response": generated_draft, "retrieved_context": context.text }`
*   **Question**: "Which lifecycle outcome best describes the current state of fulfilling the user's request?"
*   **Criteria**:
    *   `ACCEPT`: "The request was successfully fulfilled or answered."
    *   `ASK_USER`: "The request is underspecified and requires clarifying questions."
    *   `ESCALATE`: "The request exceeds the assistant's boundaries, capabilities, or safety guidelines."
    *   `REPAIR`: "The drafted response failed internal constraints and must be regenerated."

---

## 6. Implementation Blueprint & Next Steps

1.  **Add TypeSafe SDK**: Add `typesafe-ai` to `pyproject.toml`.
2.  **Refactor `fake_generate`**: Break the monolith into a router function utilizing `typesafe.choice()` to determine intent.
3.  **Upgrade Memory Reranking**: Inject a TypeSafe `Score` batch job into `build_note_context`, moving from `updated_at` ordering to semantic relevance ordering.
4.  **Wire Verification Boundaries**: Ensure that any mutation (`create_task`, `create_reminder`) derived from conversational input is fronted by a `typesafe.noul()` verification guard to prevent hallucinated side-effects.

**Verdict**: The current deterministic routing in Karmi is fundamentally unscalable for a natural language agent. By treating AI as discrete, composable primitives (TypeSafe), the backend code retains complete structural control while benefiting from deep semantic capabilities.
