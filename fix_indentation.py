with open('app/services/user_sms_service.py', 'r') as f:
    content = f.read()

# Fix the misaligned else statement
content = content.replace('            else:', '            else:')

with open('app/services/user_sms_service.py', 'w') as f:
    f.write(content)

print("✅ Fixed indentation")
