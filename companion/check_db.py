from database import get_recent_downloads


downloads = get_recent_downloads()

for download in downloads:
    print("=" * 60)

    print("Chrome ID:", download["chrome_download_id"])
    print("Filename:", download["original_filename"])
    print("Path:", download["original_path"])
    print("URL:", download["url"])
    print("Type:", download["mime_type"])
    print("Size:", download["file_size"])
    print("Status:", download["status"])