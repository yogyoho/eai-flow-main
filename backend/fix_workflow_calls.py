"""Fix all workflow.execute_activity() calls to use args=[...] syntax.
The function reference is on the line after execute_activity(, then args follow.
Skip the first positional argument (the activity function reference).
"""
import re

with open("app/extensions/workflow/temporal/workflows.py", "r") as f:
    content = f.read()

lines = content.split("\n")
fixed_count = 0
i = 0
new_lines = []

while i < len(lines):
    line = lines[i]
    new_lines.append(line)

    stripped = line.strip()
    if "workflow.execute_activity(" in stripped:
        # Find the function reference line (first line after the call)
        func_line_idx = None
        func_indent = None
        args = []
        timeout_line = None

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            s = next_line.strip()

            # Empty/comment: skip
            if not s or s.startswith("#"):
                j += 1
                continue

            # Start of a keyword arg like start_to_close_timeout=
            if s.startswith("start_to_close_timeout="):
                timeout_line = j
                break

            # If we haven't found the func ref yet, this is it
            if func_line_idx is None:
                func_line_idx = j
                func_indent = len(next_line) - len(next_line.lstrip())
                j += 1
                continue

            # Otherwise, this is a positional arg
            arg = s.rstrip(",")
            args.append(arg)
            j += 1

        if args and timeout_line is not None:
            # Remove the lines we'll replace
            new_lines.pop()  # remove the execute_activity line we added
            new_lines.append(line)  # re-add execute_activity line

            # Add the function reference line back
            new_lines.append(lines[func_line_idx])

            # Add args=[...]
            indent = " " * func_indent
            args_str = ", ".join(args)
            new_lines.append(f"{indent}    args=[{args_str}],")

            # Add the timeout line
            new_lines.append(lines[timeout_line])

            # Skip ahead
            i = timeout_line
            fixed_count += 1

    i += 1

content_fixed = "\n".join(new_lines)
with open("app/extensions/workflow/temporal/workflows.py", "w") as f:
    f.write(content_fixed)

print(f"Fixed {fixed_count} execute_activity() calls")
