# ERD (Entity Relationship Diagram)

This folder contains the Mermaid ER diagram for the Examination System database structure.

## Files

- `examination_system_erd.mmd`: Mermaid ERD source file.

## How to view

- Paste the contents of `examination_system_erd.mmd` into the Mermaid Live Editor.
- Or render it in Markdown viewers that support Mermaid `erDiagram`.

## Notes

- The ERD is derived from Django models in `examination_system/accounts/models.py` and `examination_system/core/models.py`.
- Many-to-many fields are shown using explicit join tables (because Django creates intermediate tables unless a custom `through` model is used).
- Relationship syntax reference: `https://mermaid.js.org/syntax/entityRelationshipDiagram.html`

