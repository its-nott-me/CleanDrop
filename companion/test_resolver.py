from files.resolver import resolve_at_path


path = r"C:\Users\admin\Downloads\images 1.jfif"

expected_identity = (
    "12747014758557690028:"
    "f8091000000070000000000000000000"
)


result = resolve_at_path(
    path,
    expected_identity
)

print(result)