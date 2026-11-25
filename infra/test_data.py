def test_staging_sqlite_volume(host):
    data = host.file("/data")
    assert data.is_directory
    assert host.file("/data/submissions.sqlite").is_file
    assert host.run("test -s /data/submissions.sqlite").rc == 0
