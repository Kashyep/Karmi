import re

content = open("src/model_lab/core.py").read()

def find_sql_injection(content):
    matches = re.finditer(r'execute\(\s*f["\'](.*?)(UPDATE|INSERT|DELETE|SELECT).*?["\']', content, re.IGNORECASE)
    for match in matches:
        print("SQL injection match:", match.group(0))

find_sql_injection(content)
