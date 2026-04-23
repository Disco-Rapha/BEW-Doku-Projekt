-- 008_chat_state_measured_tokens.sql
-- Reale Kontext-Groesse aus Foundry-Response speichern.
--
-- Bisher berechnen wir token_estimate aus chat_messages.token_count
-- (= chars/4-Schaetzung). Das unterschaetzt systematisch, weil
-- Reasoning-Traces, die Foundry via previous_response_id zwischen Turns
-- haelt, und der feste Overhead (System-Prompt + Tool-Definitionen) in
-- dieser Summe nicht drin sind.
--
-- Ab hier speichern wir zusaetzlich measured_context_tokens — die Zahl,
-- die Azure selbst in usage.input_tokens liefert (= alles was im naechsten
-- Call wirklich in den Context fliesst, inklusive System-Prompt,
-- Tool-Schemas und Reasoning-Trace). Das ist unser Ground-Truth fuer
-- Fuellstands-Anzeige + Auto-Compact-Trigger.

ALTER TABLE project_chat_state
    ADD COLUMN measured_context_tokens INTEGER;

ALTER TABLE project_chat_state
    ADD COLUMN measured_at TEXT;

-- Das Modell, gegen das gemessen wurde. Wenn sich das Deployment aendert
-- (z.B. gpt-5.1 -> gpt-5.2), ist der letzte Messwert bezugslos und wir
-- fallen zurueck auf die Schaetzung, bis der naechste Turn frische Daten
-- liefert.
ALTER TABLE project_chat_state
    ADD COLUMN measured_model TEXT;

-- Cached-Input-Tokens aus derselben Azure-Response. Zusammen mit
-- measured_context_tokens laesst sich die Cache-Hitrate ableiten — wichtig
-- fuer die Kosten-Kalibrierung (Backlog: Cached-Input-Rabatt).
ALTER TABLE project_chat_state
    ADD COLUMN measured_cached_tokens INTEGER;
