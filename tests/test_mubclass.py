import io
import sys
from pathlib import Path

import pytest

from module_used_by.mubclass import MUB, process_args


def test_find_assembly_dirs():
    mub = MUB(".")
    mub.find_assembly_dirs()
    dirs = [x.name for x in mub.otherdirs]
    assert("tests" in dirs)
    assert("module_used_by" in dirs)
    assert("blah" not in dirs)


def test_find_assembly_dirs_in_fixtures():
    mub = MUB(".")
    try:
        mub.find_assembly_dirs("tests/fixtures")
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    dirs = [x.name for x in mub.otherdirs]
    assert("a" in dirs)
    assert("b" in dirs)
    assert("modules" not in dirs)


def test_find_assembly_dirs_file_not_found():
    mub = MUB(".")
    with pytest.raises(FileNotFoundError) as err:
        mub.find_assembly_dirs("tests/does_not_exist")
    assert("Repodir does not exist" in str(err.value))


def test_find_assembly_files():
    mub = MUB(".")
    try:
        mub.find_assembly_dirs("tests/fixtures")
        mub.find_assembly_files()
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    assert("assem-a.adoc" in x.name for x in mub.assemblies)
    assert("assem-b.adoc" in x.name for x in mub.assemblies)
    assert("modules" not in x.name for x in mub.assemblies)


def test_get_used_by_from_search():
    mub = MUB(".")
    try:
        mub.find_assembly_dirs("tests/fixtures")
        mub.find_assembly_files()
        mub.get_used_by_from_search()
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    assert("modules/a.adoc" in mub.used_by.keys())
    assert("assem-a.adoc" in x for x in mub.used_by["modules/a.adoc"])
    assert("assem-b.adoc" in x for x in mub.used_by["modules/a.adoc"])
    assert("assem-c.adoc" not in x for x in mub.used_by["modules/a.adoc"])


def test_get_used_by_from_comments():
    no_comment = """[id="some-id"]

    = Look at me breaking the rules

    Some para.
    """.split('\n')

    one = """// Module included in the following assemblies:
    //
    // * net/cookies/recipe.adoc

    """.split('\n')

    two = """// Module included in the following assemblies:
    //
    // * net/cookies/recipe.adoc
    //*storage/wooden/trunk.adoc
    // *chess/knight.adoc
    """.split('\n')

    mub = MUB(".")
    line_no, lines = mub.get_used_by_from_comments(no_comment)
    assert(len(lines) == 0)

    line_no, one_resp = mub.get_used_by_from_comments(one)
    assert(line_no == 3)
    assert(len(one_resp) == 1)
    assert("net/cookies/recipe.adoc" in one_resp)

    line_no, two_resp = mub.get_used_by_from_comments(two)
    assert(len(two_resp) == 3)
    assert("storage/wooden/trunk.adoc" in two_resp)
    assert("chess/knight.adoc" in two_resp)


def test_update_used_by_info_stale():
    mub = MUB(".")
    modlines = Path("tests/fixtures/modules/a.adoc")
    with modlines.open() as f:
        orig = f.readlines()

    try:
        mub.find_assembly_dirs("tests/fixtures")
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    mub.find_assembly_files()
    mub.get_used_by_from_search()
    lines = mub.update_used_by_info(modlines, orig)

    assert(lines[2] == '// * a/assem-a.adoc\n')
    assert(lines[3] == '// * b/assem-b.adoc\n')
    assert(lines[4] == '\n')
    assert(lines[5] == '[id="a_{context}"]\n')


def test_get_includes_from_file():
    mub = MUB(".")
    assembly = Path("tests/fixtures/b/assem-c.adoc")
    with assembly.open() as f:
        lines = f.readlines()
    included_modules = mub.get_includes_from_file(lines)
    assert("modules/c.adoc" in included_modules)


def test_update_used_by_info_no_change():
    mub = MUB(".")
    modlines = Path("tests/fixtures/modules/b.adoc")
    with modlines.open() as f:
        orig = f.readlines()

    try:
        mub.find_assembly_dirs("tests/fixtures")
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    mub.find_assembly_files()
    mub.get_used_by_from_search()
    lines = mub.update_used_by_info(modlines, orig)

    assert(None == lines)


def test_update_used_by_info_not_comment():
    mub = MUB(".")
    modlines = Path("tests/fixtures/modules/c.adoc")
    with modlines.open() as f:
        orig = f.readlines()

    try:
        mub.find_assembly_dirs("tests/fixtures")
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    mub.find_assembly_files()
    mub.get_used_by_from_search()
    lines = mub.update_used_by_info(modlines, orig)

    assert(lines[0] == '// Module included in the following assemblies:\n')
    assert(lines[1] == '//\n')
    assert(lines[2] == '// * b/assem-c.adoc\n')
    assert(lines[3] == '\n')
    assert(lines[4] == '[id="c_{context}"]\n')
    assert(lines[5] == '= Module C\n')


def test_update_used_by_info_not_used():
    mub = MUB(".")
    modlines = Path("tests/fixtures/modules/notused.adoc")
    with modlines.open() as f:
        orig = f.readlines()

    try:
        mub.find_assembly_dirs("tests/fixtures")
    except FileNotFoundError as err:
        print("Error: ", err)
        sys.exit(2)
    mub.find_assembly_files()
    mub.get_used_by_from_search()
    lines = mub.update_used_by_info(modlines, orig)

    # Nothing is returned with the logic that the file
    # should just be left as-is.
    assert(None == lines)


def test_process_args_files():
    args = ["one", "two", "three"]
    result = process_args(args)
    assert("one" in result["files"])
    assert("foo" not in result["files"])
    assert(len(result["exclude_dirs"]) == 0)
    assert(len(result["exclude_files"]) == 0)


def test_process_args_exclude_dirs():
    args = ["--exclude-dir=foo", "--exclude-dir=bar", "one", "two", "three"]
    result = process_args(args)
    assert("one" in result["files"])
    assert("foo" not in result["files"])
    assert("bar" not in result["files"])
    assert("foo" in result["exclude_dirs"])
    assert("bar" in result["exclude_dirs"])
    assert(len(result["exclude_files"]) == 0)


def test_process_args_exclude_dirs():
    args = ["--exclude-file=some/file.adoc",
            "--exclude-dir=bar", "one", "two", "three"]
    result = process_args(args)
    assert("one" in result["files"])
    assert("bar" not in result["files"])
    assert("some/file.adoc" in result["exclude_files"])
    assert("bar" in result["exclude_dirs"])
