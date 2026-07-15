from pathlib import Path
import textwrap
import pytest
from core.test_discovery import collect_tests
from core.test_tree import build_test_tree
from core.campaign import load_campaign


def make_suite(tmp_path: Path):
    (tmp_path/'test_sample.py').write_text(textwrap.dedent('''
        import pytest
        def test_ok(): assert True
        def test_fail(): assert False
        @pytest.mark.parametrize("value", [1, 2])
        def test_param(value): assert value > 0
        class TestGroup:
            def test_method(self): assert True
    '''), encoding='utf-8')


def leaves(nodes):
    out=[]; stack=list(nodes)
    while stack:
        n=stack.pop()
        if n.nodeid: out.append(n.nodeid)
        stack.extend(n.children)
    return out


def test_discovery_and_tree(tmp_path):
    make_suite(tmp_path)
    nodeids=collect_tests(str(tmp_path))
    assert len(nodeids)==5
    assert all(not Path(n.split('::')[0]).is_absolute() for n in nodeids)
    roots=build_test_tree(nodeids)
    assert sorted(leaves(roots))==sorted(nodeids)


def test_empty_workspace(tmp_path):
    assert collect_tests(str(tmp_path)) == []


def test_collection_error(tmp_path):
    (tmp_path/'test_broken.py').write_text('this is invalid python !!!', encoding='utf-8')
    with pytest.raises(RuntimeError): collect_tests(str(tmp_path))


def test_campaign_resolution_and_repeats(tmp_path):
    (tmp_path/'tests').mkdir(); (tmp_path/'tests/test_a.py').write_text('def test_a(): pass')
    yml=tmp_path/'campaign.yml'
    yml.write_text(textwrap.dedent('''
      name: Demo
      workspace: .
      pythonpath: [tests]
      scenarios:
        - name: S1
          setup: python -c "print('ok')"
          tests:
            - nodeid: tests/test_a.py::test_a
              repeat: 3
    '''), encoding='utf-8')
    c=load_campaign(str(yml))
    assert c.name=='Demo' and Path(c.workspace)==tmp_path.resolve()
    assert c.scenarios[0].tests[0].repeat==3
    assert c.pythonpath[0]==str(tmp_path.resolve())


def test_invalid_campaign(tmp_path):
    p=tmp_path/'bad.yml'; p.write_text('scenarios: nope', encoding='utf-8')
    with pytest.raises(ValueError): load_campaign(str(p))


def test_packaged_workspace_exposes_parametrized_examples():
    """Le workspace livré doit afficher les cas @pytest.mark.parametrize dans la GUI."""
    project_root = Path(__file__).resolve().parents[1]
    nodeids = collect_tests(str(project_root))
    expected = {
        "testSuite1/test_parametrized_selection.py::test_addition_parametree[small]",
        "testSuite1/test_parametrized_selection.py::test_addition_parametree[medium]",
        "testSuite1/test_parametrized_selection.py::test_addition_parametree[large]",
    }
    assert expected.issubset(set(nodeids))
