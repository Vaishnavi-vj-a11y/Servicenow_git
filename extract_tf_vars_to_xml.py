
import sys
import os
import re
import xml.etree.ElementTree as ET

"""
Improved extractor:
 - Detects and logs whether locals and provider blocks are found
 - Parses multi-line values for simple assignments
 - Writes parsed content to terraform_vars.xml
"""

def strip_comments(line: str) -> str:
    # Remove inline comments (# or //), keep content before comment
    line = re.split(r'\s#', line, maxsplit=1)[0]
    line = re.split(r'\s//', line, maxsplit=1)[0]
    return line.rstrip()

def find_block_spans(content: str, header_regex: str):
    """Return list of (start,end) for block contents following header."""
    spans = []
    for m in re.finditer(header_regex, content, flags=re.IGNORECASE):
        # find first '{' after match
        pos = content.find('{', m.end())
        if pos == -1:
            continue
        depth = 0
        i = pos
        while i < len(content):
            c = content[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    spans.append((pos + 1, i))  # inner content only
                    break
            i += 1
    return spans

def collect_simple_assignments(block_text: str) -> dict:
    """
    Collects key = value assignments.
    Handles values spanning multiple lines until a line ends with an unbalanced quote or comma.
    Ignores nested blocks like "features {}" or "os_disk { ... }".
    """
    result = {}
    lines = block_text.splitlines()

    # Remove lines that are pure block starters/enders to avoid nested objects
    cleaned = []
    brace_depth = 0
    for raw in lines:
        s = strip_comments(raw)
        if not s.strip():
            continue
        # crude brace tracking to skip nested blocks
        brace_depth += s.count('{')
        brace_depth -= s.count('}')
        if brace_depth > 0 and not re.match(r'^\s*[A-Za-z0-9_]+\s*=\s*', s):
            # inside nested block and not an assignment
            continue
        cleaned.append(s)

    # Reconstruct multi-line "key = value" statements
    buf = []
    for s in cleaned:
        if re.match(r'^\s*[A-Za-z0-9_]+\s*=\s*', s) and not buf:
            buf = [s]
        elif buf:
            buf.append(s)
            # if line ends with closing quote or looks complete, try finalize
            joined = ' '.join(buf).strip()
            if balanced_assignment(joined):
                parse_assignment_line(joined, result)
                buf = []
        else:
            # single dangling non-assignment line: ignore
            pass
    # handle leftover buffer
    if buf:
        joined = ' '.join(buf).strip()
        parse_assignment_line(joined, result)

    return result

def balanced_assignment(s: str) -> bool:
    # naive check: if quotes balanced and parentheses balanced, consider complete
    dq = s.count('"')
    sq = s.count("'")
    return dq % 2 == 0 and sq % 2 == 0

def parse_assignment_line(line: str, out: dict):
    m = re.match(r'^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$', line)
    if not m:
        return
    key, val = m.group(1), m.group(2).strip()

    # Trim trailing commas
    if val.endswith(','):
        val = val[:-1].strip()

    # Remove quotes
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
        val = val[1:-1]
    elif val.lower() in ('true', 'false'):
        val = (val.lower() == 'true')
    else:
        # Try numbers; else leave string (expressions remain as-is)
        try:
            if '.' in val:
                val = float(val)
            else:
                val = int(val)
        except ValueError:
            pass
    out[key] = val

def infer_type(v) -> str:
    if isinstance(v, bool): return "boolean"
    if isinstance(v, (int, float)): return "number"
    return "string"

def pretty_print_xml(elem, level=0):
    indent = "\n" + ("  " * level)
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        for child in elem:
            pretty_print_xml(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent

def write_xml(locals_dict: dict, provider_dict: dict, out_path: str):
    root = ET.Element("TerraformVariables")

    locals_el = ET.SubElement(root, "Locals")
    for k, v in locals_dict.items():
        var_el = ET.SubElement(locals_el, "Variable")
        ET.SubElement(var_el, "Name").text = str(k)
        ET.SubElement(var_el, "Value").text = str(v)
        ET.SubElement(var_el, "Type").text = infer_type(v)

    provider_el = ET.SubElement(root, "Provider")
    ET.SubElement(provider_el, "Name").text = "azurerm"

    skip_keys = {"client_secret"}  # avoid plaintext secrets
    for k, v in provider_dict.items():
        if k in skip_keys:
            continue
        var_el = ET.SubElement(provider_el, "Setting")
        ET.SubElement(var_el, "Name").text = str(k)
        ET.SubElement(var_el, "Value").text = str(v)
        ET.SubElement(var_el, "Type").text = infer_type(v)
        ET.SubElement(var_el, "Sensitive").text = "true" if k in {"tenant_id","subscription_id","client_id"} else "false"

    pretty_print_xml(root)
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)

def main():
    tf_path = sys.argv[1] if len(sys.argv) >= 2 else "main.tf"

    if not os.path.isfile(tf_path):
        print(f"ERROR: File not found: {tf_path}")
        print("Tip: python .\\extract_tf_vars_to_xml.py .\\main.tf")
        sys.exit(1)

    with open(tf_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Normalize any encoded angle brackets
    content = content.replace("&gt;", ">").replace("&lt;", "<")

    # Find locals
    locals_spans = find_block_spans(content, r'\blocals\s*\{')
    print(f"[info] locals blocks found: {len(locals_spans)}")
    locals_dict = {}
    for i, (start, end) in enumerate(locals_spans, 1):
        block = content[start:end]
        parsed = collect_simple_assignments(block)
        print(f"[info] locals#{i} parsed keys: {list(parsed.keys())}")
        locals_dict.update(parsed)

    # Find provider "azurerm"
    provider_spans = find_block_spans(content, r'\bprovider\s+"azurerm"\s*\{')
    print(f"[info] azurerm provider blocks found: {len(provider_spans)}")
    provider_dict = {}
    for i, (start, end) in enumerate(provider_spans, 1):
        block = content[start:end]
        parsed = collect_simple_assignments(block)
        print(f"[info] provider#{i} parsed keys: {list(parsed.keys())}")
        provider_dict.update(parsed)

    out_path = "terraform_vars.xml"
    write_xml(locals_dict, provider_dict, out_path)

    print(f"\n✅ Done. Wrote variables/settings to: {out_path}")
    print(f"   • Locals extracted: {len(locals_dict)}")
    shown_provider = {k: v for k, v in provider_dict.items() if k != "client_secret"}
    print(f"   • Provider settings extracted (excluding client_secret): {len(shown_provider)}")
    if "client_secret" in provider_dict:
        print("   • client_secret detected but not written (skipped by default).")

if __name__ == "__main__":
    main()
