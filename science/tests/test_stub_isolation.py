"""The isolation contract itself, asserted rather than assumed.

conftest's hooks FAIL any test that finds a fake in sys.modules outside the fixture
that owns it. These tests state the contract from the other side: a test that never
asked for a stub must see the real module, and a test that did ask must not leak it
to the next one.

This is the regression guard for F08. Without it the fix decays the first time
someone adds a module that installs a global stub — which is how F08 arrived.
"""
import sys

def test_a_test_that_did_not_ask_for_a_stub_sees_no_stub(stub_contract):
    assert stub_contract.stubbed() == []


def test_the_real_requests_is_importable_when_no_fixture_faked_it(stub_contract):
    import requests
    assert not getattr(requests, stub_contract.marker, False)
    assert hasattr(requests, "Session"), "this should be the real library"


def test_a_fixture_stub_is_visible_only_inside_the_test_that_asked(esm, stub_contract):
    """`esm` fakes torch/transformers/requests for this test only."""
    assert sorted(stub_contract.stubbed()) == ["requests", "torch", "transformers"]
    assert esm.valid_accession("P01308") == "P01308"


def test_the_previous_test_did_not_leak_its_stubs(stub_contract):
    """Runs after the one above. The hooks would already have failed it; this states
    the property in the suite itself so it survives a hook refactor."""
    assert stub_contract.stubbed() == []
    import requests
    assert hasattr(requests, "Session")
