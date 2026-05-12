#!/usr/bin/env python3
import re, json, sys, pathlib
script_path = pathlib.Path('skills/agent-le-boss/scripts/init-sanctum.py')
params = {'exists': script_path.exists(), 'skill_name': None, 'template_files': [], 'skill_only_files': [], 'evolvable': None}
if script_path.exists():
    content = script_path.read_text(encoding='utf-8')
    match = re.search(r'SKILL_NAME\s*=\s*["\']([^"\']+)["\']', content)
    if match: params['skill_name'] = match.group(1)
    tmpl_match = re.search(r'TEMPLATE_FILES\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if tmpl_match:
        params['template_files'] = re.findall(r'["\']([^"\']+)["\']', tmpl_match.group(1))
    only_match = re.search(r'SKILL_ONLY_FILES\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if only_match:
        params['skill_only_files'] = re.findall(r'["\']([^"\']+)["\']', only_match.group(1))
    evolvable_match = re.search(r'EVOLVABLE\s*=\s*(True|False)', content)
    if evolvable_match:
        params['evolvable'] = evolvable_match.group(1) == 'True'
print(json.dumps(params, indent=2))