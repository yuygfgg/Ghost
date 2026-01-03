from packages.core.magnet_metadata import MagnetFile, build_file_tree


def test_build_file_tree_aggregates_sizes_and_counts():
    files = [
        MagnetFile(path="dir/a.txt", size_bytes=100),
        MagnetFile(path="dir/sub/b.bin", size_bytes=200),
        MagnetFile(path="c.bin", size_bytes=50),
    ]
    tree = build_file_tree(files)

    assert [n["name"] for n in tree] == ["dir", "c.bin"]
    dir_node = tree[0]
    assert dir_node["type"] == "dir"
    assert dir_node["size_bytes"] == 300
    assert dir_node["file_count"] == 2
    assert dir_node["children"]
    assert "size_human" in dir_node

    file_node = tree[1]
    assert file_node["type"] == "file"
    assert file_node["size_bytes"] == 50
    assert "size_human" in file_node
