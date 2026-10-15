# Add-on modes

Drop a Markdown file here (on the server: `/opt/emile-local/addenda/`) and it appears as a mode in the menu next to the course picker. The add-on files themselves are **not** kept in this repository (`.gitignore`), so an add-on can belong to someone else, for example a college, while Emile stays its own.

```
# Mode name
Required headings: Section A | Section B | Section C
Starter: Card title | one-line description | Prompt text with [blanks]\nand new lines written as \n
Starter: ...
---
Instructions for Emile in this mode (appended to Emile's system prompt).
```

- **Required headings** is a rule in code: every deliverable in this mode must contain each one as a `##` heading, or it is sent back for one revision and the missing sections are shown.
- **Starter** lines become the template cards while the mode is on.
- Restart is not needed; the app reads the folder on every request.
