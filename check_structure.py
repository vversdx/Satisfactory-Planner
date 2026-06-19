import json

with open('ru.json', 'r', encoding='utf-16') as f:
    data = json.load(f)

print(f"Total sections: {len(data)}")

# Find all unique NativeClass values
classes = set()
for s in data:
    nc = s.get('NativeClass', '')
    # Extract just the class name
    if "'" in nc:
        parts = nc.split("'")
        if len(parts) >= 2:
            classes.add(parts[1])

print("\nUnique NativeClass values:")
for c in sorted(classes):
    count = sum(1 for s in data if c in s.get('NativeClass', ''))
    # Count classes inside
    inner_count = len(s.get('Classes', []))
    print(f"  {c}: {count} sections")
    if inner_count:
        print(f"    -> {inner_count} items inside")
