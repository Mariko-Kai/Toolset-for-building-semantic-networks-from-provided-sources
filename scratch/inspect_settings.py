import llama_cpp.server.app as server_app
print("Settings fields:")
for field_name, field in server_app.Settings.model_fields.items():
    print(f"  {field_name}: {field.annotation}")
