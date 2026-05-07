-- 009_chat_message_attachments.sql
-- ===========================================================================
-- Chat-Anhaenge: User darf Screenshots / kleine Text-Files an eine
-- Chat-Nachricht haengen. Datei wird unter
-- <project>/.disco/chat-attachments/<uuid>.<ext> abgelegt; pro Message
-- speichern wir hier nur die Referenzen.
-- ===========================================================================

-- attachments_json: JSON-Array von Objekten, je
--   {
--     "id":        "<uuid>",
--     "filename":  "screenshot.png",
--     "mime_type": "image/png",
--     "size":      123456,
--     "kind":      "image" | "text",
--     "rel_path":  ".disco/chat-attachments/<uuid>.png"   (relativ zum Projekt)
--   }
-- Bewusst KEIN content/data hier — Datei lebt im Filesystem, das ist die
-- Wahrheitsquelle. Bei NULL/leerem Array: keine Anhaenge (Default).
ALTER TABLE chat_messages ADD COLUMN attachments_json TEXT;
