from files.identity import get_file_identity, identity_key


path = r"C:\Users\admin\Downloads\sheep.jfif"


identity = get_file_identity(path)

print("Identity:")
print(identity)

print()
print("Identity key:")
print(identity_key(identity))