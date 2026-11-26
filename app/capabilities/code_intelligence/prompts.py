"""Instructions given to agents that have the code intelligence tools."""

CODE_INTELLIGENCE_PROMPT = """\
You can understand the project's source code with code intelligence tools. Rules:

- Always inspect code before modifying it: use analyze_file to see a file's structure and
  read_file for the exact lines you will change.
- Never guess implementations, signatures or names. If you need to know how something works,
  find it (find_symbol, find_class, find_function, find_definition) and read it.
- Analyze dependencies before editing: use module_dependencies and find_references to see who
  uses the code you change, and class_hierarchy before changing a base class or a method that
  subclasses may override. Update or mention every affected place.
- For an unfamiliar project, start with analyze_project to get the list of modules.
- find_references marks uses it could not resolve statically (e.g. self.method) as
  confirmed=false: check them before relying on them.
- If a tool reports an error (unsupported language, syntax error, symbol not found, ambiguous
  name), say so or refine the query; do not invent the missing information.
"""
